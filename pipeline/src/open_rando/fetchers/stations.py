from __future__ import annotations

import logging
import time

from shapely.geometry import LineString, MultiLineString

from open_rando.config import (
    MAX_STATION_BBOX_DEGREES,
    OVERPASS_COOLDOWN_SECONDS,
    OVERPASS_TIMEOUT_SECONDS,
)
from open_rando.fetchers.overpass import query_overpass
from open_rando.models import Station

logger = logging.getLogger("open_rando")

BOUNDING_BOX_MARGIN_DEGREES = 0.05  # ~5km


def fetch_stations(trail: LineString | MultiLineString) -> tuple[list[Station], bool]:
    """Fetch railway stations and halts near the trail.

    For large trails (bbox > MAX_STATION_BBOX_DEGREES), splits into chunks
    to avoid Overpass timeouts.

    Returns (stations, all_cached) where all_cached is True if every Overpass
    query was served from cache.
    """
    bounds = trail.bounds
    min_lon, min_lat, max_lon, max_lat = bounds
    width = max_lon - min_lon
    height = max_lat - min_lat

    if width > MAX_STATION_BBOX_DEGREES or height > MAX_STATION_BBOX_DEGREES:
        return _fetch_stations_chunked(trail)

    return _fetch_stations_bbox(min_lat, min_lon, max_lat, max_lon)


def _fetch_stations_bbox(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> tuple[list[Station], bool]:
    """Fetch stations within a single bounding box."""
    south = min_lat - BOUNDING_BOX_MARGIN_DEGREES
    west = min_lon - BOUNDING_BOX_MARGIN_DEGREES
    north = max_lat + BOUNDING_BOX_MARGIN_DEGREES
    east = max_lon + BOUNDING_BOX_MARGIN_DEGREES

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


def _fetch_stations_chunked(trail: LineString | MultiLineString) -> tuple[list[Station], bool]:
    """Split trail into chunks and fetch stations for each chunk's bbox."""
    segments = list(trail.geoms) if isinstance(trail, MultiLineString) else [trail]

    # Further split long segments into ~2 degree chunks
    chunks: list[tuple[float, float, float, float]] = []
    for segment in segments:
        segment_bounds = segment.bounds
        segment_width = segment_bounds[2] - segment_bounds[0]
        segment_height = segment_bounds[3] - segment_bounds[1]

        if segment_width <= MAX_STATION_BBOX_DEGREES and segment_height <= MAX_STATION_BBOX_DEGREES:
            chunks.append(segment_bounds)
        else:
            # Split segment into sub-chunks by interpolating along the line
            coords = list(segment.coords)
            chunk_coords: list[tuple[float, float]] = [coords[0]]
            for coord in coords[1:]:
                chunk_coords.append(coord)
                current_bounds = _coords_bounds(chunk_coords)
                width = current_bounds[2] - current_bounds[0]
                height = current_bounds[3] - current_bounds[1]
                if width > MAX_STATION_BBOX_DEGREES or height > MAX_STATION_BBOX_DEGREES:
                    # Save current chunk (minus last point) and start new one
                    chunks.append(_coords_bounds(chunk_coords[:-1]))
                    chunk_coords = [chunk_coords[-2], coord]
            if len(chunk_coords) >= 2:
                chunks.append(_coords_bounds(chunk_coords))

    logger.info("Fetching stations in %d bbox chunks", len(chunks))

    seen_codes: set[str] = set()
    all_stations: list[Station] = []
    all_cached = True
    previous_was_cached = True

    for chunk_index, (min_lon, min_lat, max_lon, max_lat) in enumerate(chunks):
        if chunk_index > 0 and not previous_was_cached:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)
        chunk_stations, cache_hit = _fetch_stations_bbox(min_lat, min_lon, max_lat, max_lon)
        previous_was_cached = cache_hit
        if not cache_hit:
            all_cached = False
        for station in chunk_stations:
            if station.code not in seen_codes:
                seen_codes.add(station.code)
                all_stations.append(station)

    logger.info("Found %d unique stations across %d chunks", len(all_stations), len(chunks))
    return all_stations, all_cached


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


def _coords_bounds(
    coords: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """Compute bounding box for a list of (lon, lat) coordinates."""
    lons = [coord[0] for coord in coords]
    lats = [coord[1] for coord in coords]
    return (min(lons), min(lats), max(lons), max(lats))


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
