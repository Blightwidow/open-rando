from __future__ import annotations

import logging

from open_rando.config import (
    OVERPASS_TIMEOUT_SECONDS,
)
from open_rando.fetchers.osm_extract import LAYER_STATIONS, open_layer
from open_rando.fetchers.overpass import query_overpass
from open_rando.models import Station

logger = logging.getLogger("open_rando")

BOUNDING_BOX_MARGIN_DEGREES = 0.05  # ~5km


def fetch_stations_in_bounds(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> tuple[list[Station], bool]:
    """Fetch stations within a bounding box (plus a margin).

    Returns (stations, all_cached): cached means served from the local extract
    or the Overpass cache.
    """
    south = min_lat - BOUNDING_BOX_MARGIN_DEGREES
    west = min_lon - BOUNDING_BOX_MARGIN_DEGREES
    north = max_lat + BOUNDING_BOX_MARGIN_DEGREES
    east = max_lon + BOUNDING_BOX_MARGIN_DEGREES

    index = open_layer(LAYER_STATIONS, (south, west, north, east))
    if index is not None:
        try:
            local_data = index.point_elements(LAYER_STATIONS, south, west, north, east)
        finally:
            index.close()
        stations = _parse_station_elements(local_data)
        logger.info("Found %d named stations in bounding box (local extract)", len(stations))
        return stations, True

    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
(
  node["railway"="station"]["disused"!="yes"]["abandoned"!="yes"]({south},{west},{north},{east});
  node["railway"="halt"]["disused"!="yes"]["abandoned"!="yes"]({south},{west},{north},{east});
  node["highway"="bus_stop"]({south},{west},{north},{east});
  node["public_transport"="platform"]["bus"="yes"]({south},{west},{north},{east});
);
out body;
"""
    data, cache_hit = query_overpass(query)
    stations = _parse_station_elements(data)
    logger.info("Found %d named stations in bounding box", len(stations))
    return stations, cache_hit


def filter_stations_by_sncf(
    stations: list[Station],
    sncf_codes: set[str],
) -> list[Station]:
    """Keep bus stops unconditionally; keep train stations only if in SNCF dataset."""
    filtered = [
        station
        for station in stations
        if station.transport_type == "bus" or station.code in sncf_codes
    ]
    dropped_count = len(stations) - len(filtered)
    if dropped_count > 0:
        dropped = [
            station
            for station in stations
            if station.transport_type == "train" and station.code not in sncf_codes
        ]
        for station in dropped:
            logger.debug("Dropped non-SNCF train station: %s (code=%s)", station.name, station.code)
        logger.info(
            "Filtered %d train stations to %d SNCF-verified (dropped %d)",
            sum(1 for station in stations if station.transport_type == "train"),
            sum(1 for station in filtered if station.transport_type == "train"),
            dropped_count,
        )
    return filtered


def _parse_station_elements(data: dict) -> list[Station]:  # type: ignore[type-arg]
    """Parse Overpass response elements into Station objects."""
    stations: list[Station] = []

    lifecycle_prefixes = (
        "disused:",
        "abandoned:",
        "razed:",
        "demolished:",
        "construction:",
        "proposed:",
    )

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name", "")
        if not name:
            continue

        if any(key.startswith(prefix) for key in tags for prefix in lifecycle_prefixes):
            logger.debug("Skipping lifecycle-prefixed station: %s", name)
            continue

        transport_type = _detect_transport_type(tags)
        code = _extract_code(tags, element["id"], transport_type)

        transit_lines_raw = tags.get("line", "") or tags.get("route_ref", "")
        transit_lines = (
            [line.strip() for line in transit_lines_raw.split(";") if line.strip()]
            if transit_lines_raw
            else []
        )

        stations.append(
            Station(
                name=name,
                code=code,
                lat=element["lat"],
                lon=element["lon"],
                distance_to_trail_meters=0.0,
                transit_lines=transit_lines,
                transport_type=transport_type,
                osm_id=f"{element.get('type', 'node')}/{element['id']}",
            )
        )

    return stations


def _detect_transport_type(tags: dict[str, str]) -> str:
    """Detect transport type from OSM tags."""
    if tags.get("railway") in ("station", "halt"):
        return "train"
    if tags.get("highway") == "bus_stop":
        return "bus"
    if tags.get("public_transport") == "platform" and tags.get("bus") == "yes":
        return "bus"
    return "train"


def _extract_code(tags: dict[str, str], element_id: int, transport_type: str) -> str:
    """Extract reference code from OSM tags based on transport type."""
    if transport_type == "train":
        return (
            tags.get("ref:SNCF")
            or tags.get("railway:ref")
            or tags.get("uic_ref")
            or str(element_id)
        )
    # Bus stops use different reference systems
    return tags.get("ref") or tags.get("ref:FR:STIF") or tags.get("ref:FR:IDFM") or str(element_id)
