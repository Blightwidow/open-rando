from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from pathlib import Path

import requests
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import nearest_points

from open_rando.config import (
    OVERPASS_API_URL,
    OVERPASS_CACHE_DIRECTORY,
    OVERPASS_CACHE_TTL_SECONDS,
    OVERPASS_TIMEOUT_SECONDS,
    OVERPASS_TRAIL_CACHE_TTL_SECONDS,
)
from open_rando.fetchers.osm_extract import LAYER_TRAILS, open_layer

logger = logging.getLogger("open_rando")

MAX_GAP_DEGREES = 0.01  # ~1km warning threshold
MAX_CHAIN_GAP_DEGREES = 0.05  # ~5km split threshold for MultiLineString
SPURIOUS_SEGMENT_MAX_KM = 10.0  # absolute upper bound for spurious-fragment drop
SPURIOUS_SEGMENT_MAX_FRACTION = 0.05  # fraction-of-longest upper bound for drop
# A segment whose BOTH ends sit this close to the main line is a branch: it
# leaves the trail at a junction and rejoins it at another. Testing the ends
# (not the nearest approach) is what separates a branch from a continuation
# that happens to run past the trail again later — a coastal path rounding a
# peninsula does exactly that.
BRANCH_MAX_DISTANCE_KM = 1.0
# A branch can be long, but a segment that carries most of the route is the
# route, whatever its ends touch.
BRANCH_MAX_FRACTION = 0.5
# A fragment this far from the main line belongs to another trail entirely.
SPURIOUS_SEGMENT_MAX_DISTANCE_KM = 25.0
EARTH_RADIUS_METERS = 6_371_000
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
                headers={"User-Agent": "open-rando-pipeline/0.1"},
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
    index = open_layer(LAYER_TRAILS)
    if index is not None:
        try:
            local_data = index.trail_elements(relation_id)
        finally:
            index.close()
        if local_data is not None:
            logger.info("Building relation %d from the local extract", relation_id)
            return _build_trail_from_elements(relation_id, local_data, cache_hit=True)
        logger.info(
            "Relation %d absent from the local extract, falling back to Overpass", relation_id
        )

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
way(r);
out geom;
rel({relation_id});
rel(r);
way(r);
out geom;
"""
    data, cache_hit = query_overpass(query, cache_ttl_seconds=OVERPASS_TRAIL_CACHE_TTL_SECONDS)
    return _build_trail_from_elements(relation_id, data, cache_hit=cache_hit)


def _build_trail_from_elements(
    relation_id: int,
    data: dict,  # type: ignore[type-arg]
    cache_hit: bool,
) -> tuple[LineString | MultiLineString, dict[str, str | int], bool]:
    """Assemble a trail geometry from Overpass-shaped relation/way elements."""
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
        segments = _chain_ways(way_coords_list)
        trail = _drop_spurious_segments(chain_linestrings(segments))
        if isinstance(trail, MultiLineString):
            total_points = sum(len(geom.coords) for geom in trail.geoms)
            logger.info("Trail has %d segments, %d points total", len(trail.geoms), total_points)
        else:
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

        segments = _chain_ways(way_coords_list)
        for index, linestring in enumerate(segments):
            label = f"{child_id}#{index}" if len(segments) > 1 else str(child_id)
            logger.info("  Child %s: %d points", label, len(linestring.coords))
        all_linestrings.extend(segments)

    if not all_linestrings:
        raise RuntimeError(f"No geometry found for relation {relation_id}")

    combined = _drop_spurious_segments(chain_linestrings(all_linestrings))
    if isinstance(combined, MultiLineString):
        total_points = sum(len(geom.coords) for geom in combined.geoms)
        logger.info("Trail has %d segments, %d points total", len(combined.geoms), total_points)
    else:
        logger.info("Trail has %d points total", len(combined.coords))
    return combined, metadata, cache_hit


def _chain_ways(way_coords_list: list[list[tuple[float, float]]]) -> list[LineString]:
    """Chain ordered ways into one or more LineStrings.

    Ways with endpoint gaps exceeding MAX_CHAIN_GAP_DEGREES start a new segment so
    disconnected ways at the tail of an OSM relation do not draw a closing line
    back across the trail.
    """
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = list(way_coords_list[0])

    for way_index in range(1, len(way_coords_list)):
        next_coords = way_coords_list[way_index]
        chain_end = current[-1]

        distance_forward = _point_distance(chain_end, next_coords[0])
        distance_reversed = _point_distance(chain_end, next_coords[-1])

        if distance_reversed < distance_forward:
            next_coords = list(reversed(next_coords))
            gap = distance_reversed
        else:
            gap = distance_forward

        if gap > MAX_CHAIN_GAP_DEGREES:
            logger.warning("Large gap (%.4f deg) before way %d, splitting trail", gap, way_index)
            segments.append(current)
            current = list(next_coords)
        elif next_coords[0] == chain_end:
            current.extend(next_coords[1:])
        else:
            if gap > MAX_GAP_DEGREES:
                logger.warning("Gap (%.4f deg) before way %d", gap, way_index)
            current.extend(next_coords)

    segments.append(current)
    return [LineString(segment) for segment in segments]


def chain_linestrings(
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


def _haversine_km(
    longitude_1: float,
    latitude_1: float,
    longitude_2: float,
    latitude_2: float,
) -> float:
    phi_1 = math.radians(latitude_1)
    phi_2 = math.radians(latitude_2)
    delta_phi = math.radians(latitude_2 - latitude_1)
    delta_lambda = math.radians(longitude_2 - longitude_1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a)) / 1000.0


def _is_branch_of(main_line: LineString, segment: LineString) -> bool:
    """Whether both ends of a segment sit on the main line.

    A branch leaves the trail at one junction and rejoins at another, so both of
    its ends touch the line. A continuation after an unmapped stretch, or a
    detached fragment, has at least one end away from it.
    """
    for longitude, latitude in (segment.coords[0], segment.coords[-1]):
        end_point = Point(longitude, latitude)
        nearest_on_line, _ = nearest_points(main_line, end_point)
        distance_km = _haversine_km(nearest_on_line.x, nearest_on_line.y, end_point.x, end_point.y)
        if distance_km > BRANCH_MAX_DISTANCE_KM:
            return False
    return True


def _distance_between_geometries_km(reference: LineString, other: LineString) -> float:
    """Shortest real-world distance between two geometries."""
    reference_point, other_point = nearest_points(reference, other)
    return _haversine_km(reference_point.x, reference_point.y, other_point.x, other_point.y)


def _segment_length_km(segment: LineString) -> float:
    coords = list(segment.coords)
    total_meters = 0.0
    for index in range(len(coords) - 1):
        longitude_1, latitude_1 = coords[index][0], coords[index][1]
        longitude_2, latitude_2 = coords[index + 1][0], coords[index + 1][1]
        phi_1 = math.radians(latitude_1)
        phi_2 = math.radians(latitude_2)
        delta_phi = math.radians(latitude_2 - latitude_1)
        delta_lambda = math.radians(longitude_2 - longitude_1)
        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2) ** 2
        )
        total_meters += 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))
    return total_meters / 1000.0


def _drop_spurious_segments(
    geom: LineString | MultiLineString,
) -> LineString | MultiLineString:
    """Drop disconnected fragments left over from OSM relation noise.

    Distance to the longest segment tells the three cases apart:

    - both ends within BRANCH_MAX_DISTANCE_KM of the main line: a branch
      leaving and rejoining the trail at junctions. Not part of the line walked
      end to end, so it goes — unless it carries most of the route's length.
    - beyond SPURIOUS_SEGMENT_MAX_DISTANCE_KM, and short: a fragment of some
      other trail the relation happens to collect. It goes too, as does any
      stub that is tiny both absolutely and relative to the longest segment.
    - in between: the trail continuing after an unmapped stretch. Kept, and the
      jump is reported as `trail_gap_km` rather than walked.
    """
    if isinstance(geom, LineString):
        return geom

    segments = list(geom.geoms)
    lengths_km = [_segment_length_km(segment) for segment in segments]
    longest_km = max(lengths_km)
    longest_index = max(range(len(segments)), key=lambda index: lengths_km[index])
    main_line = segments[longest_index]
    fraction_threshold_km = longest_km * SPURIOUS_SEGMENT_MAX_FRACTION

    kept: list[LineString] = []
    for index, (segment, length_km) in enumerate(zip(segments, lengths_km, strict=True)):
        if index == longest_index:
            kept.append(segment)
            continue

        distance_km = _distance_between_geometries_km(main_line, segment)

        if length_km < longest_km * BRANCH_MAX_FRACTION and _is_branch_of(main_line, segment):
            logger.info(
                "Dropping branch segment (%.2f km, both ends on the trail)",
                length_km,
            )
            continue

        if length_km < SPURIOUS_SEGMENT_MAX_KM and length_km < fraction_threshold_km:
            logger.info("Dropping spurious segment (%.2f km)", length_km)
            continue

        is_short = length_km < SPURIOUS_SEGMENT_MAX_KM or length_km < fraction_threshold_km
        if is_short and distance_km > SPURIOUS_SEGMENT_MAX_DISTANCE_KM:
            logger.info(
                "Dropping detached segment (%.2f km, %.0f km from the main line)",
                length_km,
                distance_km,
            )
            continue

        kept.append(segment)

    if not kept:
        longest_index = max(range(len(segments)), key=lambda i: lengths_km[i])
        return segments[longest_index]
    if len(kept) == 1:
        return kept[0]
    return MultiLineString(kept)
