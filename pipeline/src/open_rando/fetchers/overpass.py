from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import requests
from shapely.geometry import LineString, MultiLineString

from open_rando.config import (
    OVERPASS_API_URL,
    OVERPASS_CACHE_DIRECTORY,
    OVERPASS_CACHE_TTL_SECONDS,
    OVERPASS_TIMEOUT_SECONDS,
    OVERPASS_TRAIL_CACHE_TTL_SECONDS,
)

logger = logging.getLogger("open_rando")

MAX_GAP_DEGREES = 0.01  # ~1km warning threshold
MAX_CHAIN_GAP_DEGREES = 0.05  # ~5km split threshold for MultiLineString
RETRY_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = 15


def query_overpass(
    query: str,
    cache_ttl_seconds: int | None = None,
) -> tuple[dict, bool]:  # type: ignore[type-arg]
    """Query Overpass API with disk caching.

    Responses are cached by query hash. Pass cache_ttl_seconds to override default TTL,
    or 0 to bypass cache entirely.

    Returns (data, cache_hit) where cache_hit is True if the response came from cache.
    """
    ttl = cache_ttl_seconds if cache_ttl_seconds is not None else OVERPASS_CACHE_TTL_SECONDS

    if ttl > 0:
        cached = _read_cache(query, ttl)
        if cached is not None:
            return cached, True

    result = _fetch_overpass(query)

    if ttl > 0:
        _write_cache(query, result)

    return result, False


def _fetch_overpass(query: str) -> dict:  # type: ignore[type-arg]
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.post(
                OVERPASS_API_URL,
                data={"data": query},
                timeout=OVERPASS_TIMEOUT_SECONDS + 30,
            )
        except requests.exceptions.Timeout:
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("Request timeout, retrying in %ds...", wait)
            time.sleep(wait)
            continue

        if response.status_code in (429, 504):
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("Overpass %d, retrying in %ds...", response.status_code, wait)
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    raise RuntimeError("Overpass API failed after retries")


def _cache_key(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()[:16]


def _cache_path(query: str) -> Path:
    cache_directory = Path(OVERPASS_CACHE_DIRECTORY).expanduser()
    cache_directory.mkdir(parents=True, exist_ok=True)
    return cache_directory / f"{_cache_key(query)}.json"


def _read_cache(query: str, ttl_seconds: int) -> dict | None:  # type: ignore[type-arg]
    path = _cache_path(query)
    if not path.exists():
        return None

    age_seconds = time.time() - path.stat().st_mtime
    if age_seconds > ttl_seconds:
        logger.info("Cache expired for %s (%.0fs old)", path.name, age_seconds)
        return None

    logger.info("Using cached response %s (%.0fs old)", path.name, age_seconds)
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _write_cache(query: str, data: dict) -> None:  # type: ignore[type-arg]
    path = _cache_path(query)
    path.write_text(json.dumps(data), encoding="utf-8")
    logger.info("Cached Overpass response to %s", path.name)


def fetch_trail(
    relation_id: int,
) -> tuple[LineString | MultiLineString, dict[str, str | int], bool]:
    """Fetch a GR superroute and return (geometry, metadata, cache_hit).

    Returns a LineString when the trail is continuous, or a MultiLineString
    when there are gaps exceeding MAX_CHAIN_GAP_DEGREES between child relations.
    The cache_hit boolean indicates whether the Overpass response came from cache.
    """
    logger.info("Fetching relation %d with full recursion...", relation_id)

    # Single query: get the superroute, its child relations, and all ways with geometry
    query = f"""
[out:json][timeout:300];
rel({relation_id});
out body;
rel({relation_id});
rel(r);
out body;
rel({relation_id});
rel(r);
way(r);
out geom;
"""
    data, cache_hit = query_overpass(query, cache_ttl_seconds=OVERPASS_TRAIL_CACHE_TTL_SECONDS)

    # Sort elements by type
    superroute = None
    child_relations: dict[int, dict] = {}  # type: ignore[type-arg]
    ways_by_id: dict[int, list[tuple[float, float]]] = {}

    for element in data.get("elements", []):
        element_type = element["type"]
        element_id = element["id"]

        if element_type == "relation" and element_id == relation_id:
            superroute = element
        elif element_type == "relation":
            child_relations[element_id] = element
        elif element_type == "way":
            geometry = element.get("geometry", [])
            if geometry:
                coords = [(point["lon"], point["lat"]) for point in geometry]
                if len(coords) >= 2:
                    ways_by_id[element_id] = coords

    if superroute is None:
        raise RuntimeError(f"Superroute {relation_id} not found")

    metadata: dict[str, str | int] = {
        "name": superroute.get("tags", {}).get("name", ""),
        "ref": superroute.get("tags", {}).get("ref", ""),
        "osm_relation_id": relation_id,
    }

    logger.info(
        "Fetched %d child relations, %d ways",
        len(child_relations),
        len(ways_by_id),
    )

    # Get ordered child relation IDs from superroute members
    child_relation_ids = [
        member["ref"] for member in superroute.get("members", []) if member["type"] == "relation"
    ]

    if not child_relation_ids:
        # Simple route (not a superroute) -- get ways directly from this relation
        logger.info("No child relations, treating as simple route")
        ordered_way_ids = [
            member["ref"] for member in superroute.get("members", []) if member["type"] == "way"
        ]
        way_coords_list = [ways_by_id[way_id] for way_id in ordered_way_ids if way_id in ways_by_id]
        if not way_coords_list:
            raise RuntimeError(f"No ways found for relation {relation_id}")
        trail = _chain_ways(way_coords_list)
        logger.info("Trail has %d points", len(trail.coords))
        return trail, metadata, cache_hit

    # Process each child relation in order
    all_linestrings: list[LineString] = []
    for child_id in child_relation_ids:
        child = child_relations.get(child_id)
        if child is None:
            logger.warning("Child relation %d not found in response", child_id)
            continue

        ordered_way_ids = [
            member["ref"] for member in child.get("members", []) if member["type"] == "way"
        ]

        way_coords_list = [ways_by_id[way_id] for way_id in ordered_way_ids if way_id in ways_by_id]
        if not way_coords_list:
            logger.warning("No ways for child relation %d", child_id)
            continue

        linestring = _chain_ways(way_coords_list)
        logger.info("  Child %d: %d points", child_id, len(linestring.coords))
        all_linestrings.append(linestring)

    if not all_linestrings:
        raise RuntimeError(f"No geometry found for relation {relation_id}")

    combined = _chain_linestrings(all_linestrings)
    if isinstance(combined, MultiLineString):
        total_points = sum(len(geom.coords) for geom in combined.geoms)
        logger.info("Trail has %d segments, %d points total", len(combined.geoms), total_points)
    else:
        logger.info("Trail has %d points total", len(combined.coords))
    return combined, metadata, cache_hit


def _chain_ways(way_coords_list: list[list[tuple[float, float]]]) -> LineString:
    """Chain ordered ways into a single LineString, handling reversal and small gaps."""
    chained: list[tuple[float, float]] = list(way_coords_list[0])

    for way_index in range(1, len(way_coords_list)):
        next_coords = way_coords_list[way_index]
        chain_end = chained[-1]

        distance_forward = _point_distance(chain_end, next_coords[0])
        distance_reversed = _point_distance(chain_end, next_coords[-1])

        if distance_forward <= distance_reversed:
            if next_coords[0] == chain_end:
                chained.extend(next_coords[1:])
            else:
                if distance_forward > MAX_GAP_DEGREES:
                    logger.warning("Gap (%.4f deg) before way %d", distance_forward, way_index)
                chained.extend(next_coords)
        else:
            reversed_coords = list(reversed(next_coords))
            if reversed_coords[0] == chain_end:
                chained.extend(reversed_coords[1:])
            else:
                if distance_reversed > MAX_GAP_DEGREES:
                    logger.warning(
                        "Gap (%.4f deg) before way %d (reversed)", distance_reversed, way_index
                    )
                chained.extend(reversed_coords)

    return LineString(chained)


def _chain_linestrings(
    linestrings: list[LineString],
) -> LineString | MultiLineString:
    """Chain multiple LineStrings (from child relations) into one or more segments.

    When the gap between consecutive child relations exceeds MAX_CHAIN_GAP_DEGREES,
    a new segment is started, resulting in a MultiLineString.
    """
    if len(linestrings) == 1:
        return linestrings[0]

    segments: list[list[tuple[float, float]]] = []
    current_coords: list[tuple[float, float]] = list(linestrings[0].coords)

    for index in range(1, len(linestrings)):
        next_coords = list(linestrings[index].coords)
        chain_end = current_coords[-1]

        distance_normal = _point_distance(chain_end, next_coords[0])
        distance_reversed = _point_distance(chain_end, next_coords[-1])

        if distance_reversed < distance_normal:
            next_coords = list(reversed(next_coords))

        gap_distance = min(distance_normal, distance_reversed)

        if gap_distance > MAX_CHAIN_GAP_DEGREES:
            logger.warning(
                "Large gap (%.4f deg) between child relations %d and %d, splitting trail",
                gap_distance,
                index - 1,
                index,
            )
            segments.append(current_coords)
            current_coords = list(next_coords)
        elif next_coords[0] == chain_end:
            current_coords.extend(next_coords[1:])
        else:
            if gap_distance > MAX_GAP_DEGREES:
                logger.warning("Gap (%.4f deg) at child relation %d", gap_distance, index)
            current_coords.extend(next_coords)

    segments.append(current_coords)

    if len(segments) == 1:
        return LineString(segments[0])

    return MultiLineString([LineString(segment) for segment in segments])


def _point_distance(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    """Euclidean distance in degrees (for comparison only)."""
    return float(((point_a[0] - point_b[0]) ** 2 + (point_a[1] - point_b[1]) ** 2) ** 0.5)
