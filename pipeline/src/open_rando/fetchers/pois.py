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
from open_rando.models import PointOfInterest

logger = logging.getLogger("open_rando")

BOUNDING_BOX_MARGIN_DEGREES = 0.03  # ~3km matches search radius
POI_ACCOMMODATION_RADIUS_METERS = 3000


def fetch_accommodation_pois(
    trail: LineString | MultiLineString,
) -> tuple[list[PointOfInterest], bool]:
    """Fetch hotels and campings within 3km of the trail.

    Returns (pois, all_cached).
    """
    bounds = trail.bounds
    min_lon, min_lat, max_lon, max_lat = bounds
    width = max_lon - min_lon
    height = max_lat - min_lat

    if width > MAX_STATION_BBOX_DEGREES or height > MAX_STATION_BBOX_DEGREES:
        return _fetch_accommodation_chunked(trail)

    return _fetch_accommodation_bbox(min_lat, min_lon, max_lat, max_lon)


def _fetch_accommodation_bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
) -> tuple[list[PointOfInterest], bool]:
    """Fetch accommodation within a single bounding box."""
    south = min_lat - BOUNDING_BOX_MARGIN_DEGREES
    west = min_lon - BOUNDING_BOX_MARGIN_DEGREES
    north = max_lat + BOUNDING_BOX_MARGIN_DEGREES
    east = max_lon + BOUNDING_BOX_MARGIN_DEGREES

    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
(
  node["tourism"="hotel"]({south},{west},{north},{east});
  node["tourism"="guest_house"]({south},{west},{north},{east});
  node["tourism"="hostel"]({south},{west},{north},{east});
  node["tourism"="camp_site"]({south},{west},{north},{east});
  way["tourism"="hotel"]({south},{west},{north},{east});
  way["tourism"="guest_house"]({south},{west},{north},{east});
  way["tourism"="hostel"]({south},{west},{north},{east});
  way["tourism"="camp_site"]({south},{west},{north},{east});
);
out center;
"""
    data, cache_hit = query_overpass(query)
    pois = _parse_accommodation_elements(data)
    logger.info("Found %d accommodation POIs in bbox", len(pois))
    return pois, cache_hit


def _fetch_accommodation_chunked(
    trail: LineString | MultiLineString,
) -> tuple[list[PointOfInterest], bool]:
    """Split trail into chunks and fetch accommodation for each."""
    segments = list(trail.geoms) if isinstance(trail, MultiLineString) else [trail]

    chunks: list[tuple[float, float, float, float]] = []
    for segment in segments:
        segment_bounds = segment.bounds
        segment_width = segment_bounds[2] - segment_bounds[0]
        segment_height = segment_bounds[3] - segment_bounds[1]

        if segment_width <= MAX_STATION_BBOX_DEGREES and segment_height <= MAX_STATION_BBOX_DEGREES:
            chunks.append(segment_bounds)
        else:
            coords = list(segment.coords)
            chunk_coords: list[tuple[float, float]] = [coords[0]]
            for coord in coords[1:]:
                chunk_coords.append(coord)
                current_bounds = _coords_bounds(chunk_coords)
                width = current_bounds[2] - current_bounds[0]
                height = current_bounds[3] - current_bounds[1]
                if width > MAX_STATION_BBOX_DEGREES or height > MAX_STATION_BBOX_DEGREES:
                    chunks.append(_coords_bounds(chunk_coords[:-1]))
                    chunk_coords = [chunk_coords[-2], coord]
            if len(chunk_coords) >= 2:
                chunks.append(_coords_bounds(chunk_coords))

    logger.info("Fetching accommodation POIs in %d bbox chunks", len(chunks))

    seen_ids: set[str] = set()
    all_pois: list[PointOfInterest] = []
    all_cached = True
    previous_was_cached = True

    for chunk_index, (min_lon, min_lat, max_lon, max_lat) in enumerate(chunks):
        if chunk_index > 0 and not previous_was_cached:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)
        chunk_pois, cache_hit = _fetch_accommodation_bbox(
            min_lat,
            min_lon,
            max_lat,
            max_lon,
        )
        previous_was_cached = cache_hit
        if not cache_hit:
            all_cached = False
        for poi in chunk_pois:
            poi_id = f"{poi.lat},{poi.lon}"
            if poi_id not in seen_ids:
                seen_ids.add(poi_id)
                all_pois.append(poi)

    logger.info(
        "Found %d unique accommodation POIs across %d chunks",
        len(all_pois),
        len(chunks),
    )
    return all_pois, all_cached


def filter_pois_by_trail_distance(
    pois: list[PointOfInterest],
    trail: LineString | MultiLineString,
    max_distance_meters: float,
) -> list[PointOfInterest]:
    """Keep only POIs within max_distance_meters of the trail."""
    from shapely.geometry import Point
    from shapely.ops import nearest_points

    filtered: list[PointOfInterest] = []
    for poi in pois:
        point = Point(poi.lon, poi.lat)
        nearest = nearest_points(trail, point)[0]
        # Approximate degrees to meters (rough, works for France ~45N)
        distance_degrees = point.distance(nearest)
        distance_meters = distance_degrees * 111_000
        if distance_meters <= max_distance_meters:
            filtered.append(poi)

    logger.info(
        "Filtered %d accommodation POIs to %d within %.0fm of trail",
        len(pois),
        len(filtered),
        max_distance_meters,
    )
    return filtered


def _coords_bounds(
    coords: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    lons = [coord[0] for coord in coords]
    lats = [coord[1] for coord in coords]
    return (min(lons), min(lats), max(lons), max(lats))


def _parse_accommodation_elements(
    data: dict,  # type: ignore[type-arg]
) -> list[PointOfInterest]:
    """Parse Overpass response into accommodation POIs."""
    pois: list[PointOfInterest] = []

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        tourism = tags.get("tourism", "")

        name = tags.get("name", "")
        if not name:
            continue

        # Get coordinates (nodes have lat/lon, ways have center)
        if "lat" in element and "lon" in element:
            lat = element["lat"]
            lon = element["lon"]
        elif "center" in element:
            lat = element["center"]["lat"]
            lon = element["center"]["lon"]
        else:
            continue

        poi_type = "camping" if tourism == "camp_site" else "hotel"
        url = tags.get("website") or tags.get("contact:website") or None

        pois.append(PointOfInterest(name=name, lat=lat, lon=lon, poi_type=poi_type, url=url))

    return pois
