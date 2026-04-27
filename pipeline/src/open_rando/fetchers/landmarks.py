from __future__ import annotations

import logging
import time
from typing import Any

from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import nearest_points

from open_rando.config import (
    MAX_STATION_BBOX_DEGREES,
    OVERPASS_COOLDOWN_SECONDS,
    OVERPASS_TIMEOUT_SECONDS,
)
from open_rando.fetchers.overpass import query_overpass
from open_rando.models import Landmark

logger = logging.getLogger("open_rando")

LANDMARK_RADIUS_METERS = 2000
LANDMARK_BBOX_MARGIN_DEGREES = 0.02  # ~2km matches search radius
MAX_LANDMARKS_PER_ROUTE = 12

_HISTORIC_KINDS = (
    "castle",
    "monument",
    "ruins",
    "memorial",
    "archaeological_site",
    "fort",
    "tower",
    "wayside_cross",
)
_TOURISM_KINDS = ("attraction", "viewpoint")
_NATURAL_KINDS = ("peak", "cliff", "cave_entrance", "waterfall")
_MAN_MADE_KINDS = ("lighthouse", "tower")


def fetch_landmarks(
    trail: LineString | MultiLineString,
) -> tuple[list[Landmark], bool]:
    """Fetch named scenic/historical features within ~2km of the trail.

    Returns (landmarks, all_cached). Capped at MAX_LANDMARKS_PER_ROUTE,
    favoring named entities and prominence.
    """
    bounds = trail.bounds
    min_lon, min_lat, max_lon, max_lat = bounds
    width = max_lon - min_lon
    height = max_lat - min_lat

    if width > MAX_STATION_BBOX_DEGREES or height > MAX_STATION_BBOX_DEGREES:
        landmarks, all_cached = _fetch_chunked(trail)
    else:
        landmarks, all_cached = _fetch_bbox(min_lat, min_lon, max_lat, max_lon)

    landmarks = _filter_by_distance(landmarks, trail, LANDMARK_RADIUS_METERS)
    landmarks = _rank_and_cap(landmarks)

    logger.info(
        "Selected %d landmarks for prompt enrichment (capped at %d)",
        len(landmarks),
        MAX_LANDMARKS_PER_ROUTE,
    )
    return landmarks, all_cached


def _fetch_bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
) -> tuple[list[Landmark], bool]:
    south = min_lat - LANDMARK_BBOX_MARGIN_DEGREES
    west = min_lon - LANDMARK_BBOX_MARGIN_DEGREES
    north = max_lat + LANDMARK_BBOX_MARGIN_DEGREES
    east = max_lon + LANDMARK_BBOX_MARGIN_DEGREES
    bbox = f"{south},{west},{north},{east}"

    selectors: list[str] = []
    for kind in _HISTORIC_KINDS:
        selectors.append(f'  node["historic"="{kind}"]({bbox});')
        selectors.append(f'  way["historic"="{kind}"]({bbox});')
    for kind in _TOURISM_KINDS:
        selectors.append(f'  node["tourism"="{kind}"]({bbox});')
        selectors.append(f'  way["tourism"="{kind}"]({bbox});')
    for kind in _NATURAL_KINDS:
        selectors.append(f'  node["natural"="{kind}"]({bbox});')
        selectors.append(f'  way["natural"="{kind}"]({bbox});')
    for kind in _MAN_MADE_KINDS:
        selectors.append(f'  node["man_made"="{kind}"]({bbox});')
        selectors.append(f'  way["man_made"="{kind}"]({bbox});')

    body = "\n".join(selectors)
    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
(
{body}
);
out center;
"""
    data, cache_hit = query_overpass(query)
    landmarks = _parse_elements(data)
    logger.info("Found %d landmarks in bbox", len(landmarks))
    return landmarks, cache_hit


def _fetch_chunked(
    trail: LineString | MultiLineString,
) -> tuple[list[Landmark], bool]:
    segments = list(trail.geoms) if isinstance(trail, MultiLineString) else [trail]

    chunks: list[tuple[float, float, float, float]] = []
    for segment in segments:
        segment_bounds = segment.bounds
        segment_width = segment_bounds[2] - segment_bounds[0]
        segment_height = segment_bounds[3] - segment_bounds[1]

        if segment_width <= MAX_STATION_BBOX_DEGREES and segment_height <= MAX_STATION_BBOX_DEGREES:
            chunks.append(segment_bounds)
            continue

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

    logger.info("Fetching landmarks in %d bbox chunks", len(chunks))

    seen_ids: set[str] = set()
    all_landmarks: list[Landmark] = []
    all_cached = True
    previous_was_cached = True

    for chunk_index, (min_lon, min_lat, max_lon, max_lat) in enumerate(chunks):
        if chunk_index > 0 and not previous_was_cached:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)
        chunk_landmarks, cache_hit = _fetch_bbox(min_lat, min_lon, max_lat, max_lon)
        previous_was_cached = cache_hit
        if not cache_hit:
            all_cached = False
        for landmark in chunk_landmarks:
            landmark_id = f"{landmark.kind}:{landmark.lat:.5f},{landmark.lon:.5f}"
            if landmark_id not in seen_ids:
                seen_ids.add(landmark_id)
                all_landmarks.append(landmark)

    return all_landmarks, all_cached


def _filter_by_distance(
    landmarks: list[Landmark],
    trail: LineString | MultiLineString,
    max_distance_meters: float,
) -> list[Landmark]:
    filtered: list[Landmark] = []
    for landmark in landmarks:
        point = Point(landmark.lon, landmark.lat)
        nearest = nearest_points(trail, point)[0]
        distance_meters = point.distance(nearest) * 111_000
        if distance_meters <= max_distance_meters:
            filtered.append(landmark)
    return filtered


def _rank_and_cap(landmarks: list[Landmark]) -> list[Landmark]:
    """Prefer named landmarks, then prominent ones, then drop excess."""

    def sort_key(landmark: Landmark) -> tuple[int, int, int]:
        has_name = 0 if landmark.name else 1
        kind_priority = _KIND_PRIORITY.get(landmark.kind, 99)
        elevation_score = -(landmark.elevation_m or 0)
        return (has_name, kind_priority, elevation_score)

    landmarks_sorted = sorted(landmarks, key=sort_key)
    return landmarks_sorted[:MAX_LANDMARKS_PER_ROUTE]


_KIND_PRIORITY: dict[str, int] = {
    "castle": 0,
    "viewpoint": 1,
    "ruins": 2,
    "fort": 3,
    "monument": 4,
    "lighthouse": 5,
    "waterfall": 6,
    "peak": 7,
    "cliff": 8,
    "cave_entrance": 9,
    "memorial": 10,
    "archaeological_site": 11,
    "attraction": 12,
    "tower": 13,
    "wayside_cross": 14,
}


def _coords_bounds(
    coords: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    lons = [coord[0] for coord in coords]
    lats = [coord[1] for coord in coords]
    return (min(lons), min(lats), max(lons), max(lats))


def _parse_elements(data: dict[str, Any]) -> list[Landmark]:
    landmarks: list[Landmark] = []

    for element in data.get("elements", []):
        tags = element.get("tags", {})

        kind = (
            tags.get("historic")
            or tags.get("tourism")
            or tags.get("natural")
            or tags.get("man_made")
            or ""
        )
        if not kind:
            continue

        name = tags.get("name", "").strip()

        if "lat" in element and "lon" in element:
            lat = element["lat"]
            lon = element["lon"]
        elif "center" in element:
            lat = element["center"]["lat"]
            lon = element["center"]["lon"]
        else:
            continue

        elevation_m: int | None = None
        elevation_tag = tags.get("ele")
        if elevation_tag:
            try:
                elevation_m = int(float(elevation_tag))
            except (TypeError, ValueError):
                elevation_m = None

        landmarks.append(Landmark(name=name, kind=kind, lat=lat, lon=lon, elevation_m=elevation_m))

    return landmarks
