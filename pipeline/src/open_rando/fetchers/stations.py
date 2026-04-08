from __future__ import annotations

import logging

from shapely.geometry import LineString

from open_rando.config import OVERPASS_TIMEOUT_SECONDS
from open_rando.fetchers.overpass import query_overpass
from open_rando.models import Station

logger = logging.getLogger("open_rando")

BOUNDING_BOX_MARGIN_DEGREES = 0.05  # ~5km


def fetch_stations(trail: LineString) -> list[Station]:
    """Fetch railway stations and halts near the trail's bounding box."""
    min_lon, min_lat, max_lon, max_lat = trail.bounds
    south = min_lat - BOUNDING_BOX_MARGIN_DEGREES
    west = min_lon - BOUNDING_BOX_MARGIN_DEGREES
    north = max_lat + BOUNDING_BOX_MARGIN_DEGREES
    east = max_lon + BOUNDING_BOX_MARGIN_DEGREES

    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
(
  node["railway"="station"]({south},{west},{north},{east});
  node["railway"="halt"]({south},{west},{north},{east});
);
out body;
"""
    data = query_overpass(query)
    stations: list[Station] = []

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name", "")
        if not name:
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

    logger.info("Found %d named stations in bounding box", len(stations))
    return stations
