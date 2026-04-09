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


def fetch_stations(trail: LineString | MultiLineString) -> list[Station]:
    """Fetch railway stations and halts near the trail.

    For large trails (bbox > MAX_STATION_BBOX_DEGREES), splits into chunks
    to avoid Overpass timeouts.
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
) -> list[Station]:
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
);
out body;
"""
    data = query_overpass(query)
    stations = _parse_station_elements(data)
    logger.info("Found %d named stations in bounding box", len(stations))
    return stations


def _fetch_stations_chunked(trail: LineString | MultiLineString) -> list[Station]:
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

    for chunk_index, (min_lon, min_lat, max_lon, max_lat) in enumerate(chunks):
        if chunk_index > 0:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)
        chunk_stations = _fetch_stations_bbox(min_lat, min_lon, max_lat, max_lon)
        for station in chunk_stations:
            if station.code not in seen_codes:
                seen_codes.add(station.code)
                all_stations.append(station)

    logger.info("Found %d unique stations across %d chunks", len(all_stations), len(chunks))
    return all_stations


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

        code = tags.get("ref:SNCF") or tags.get("uic_ref") or str(element["id"])

        transit_lines_raw = tags.get("line", "")
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
            )
        )

    return stations
