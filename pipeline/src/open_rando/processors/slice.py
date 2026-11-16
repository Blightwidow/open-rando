from __future__ import annotations

import math
from collections.abc import Iterable

from shapely.geometry import LineString, MultiLineString
from shapely.ops import substring

EARTH_RADIUS_METERS = 6_371_000


def extract_substring_segments(
    trail: LineString | MultiLineString,
    start_fraction: float,
    end_fraction: float,
) -> list[LineString]:
    """Clip the trail between two normalized fractions, one piece per segment.

    Fractions are relative to cumulative segment lengths (the system used by
    match_stations_to_trail). Keeping the pieces apart matters for measuring:
    the straight jump between two segments is not walkable trail.
    """
    if isinstance(trail, LineString):
        trail_length = trail.length
        clipped = substring(trail, start_fraction * trail_length, end_fraction * trail_length)
        return [clipped] if isinstance(clipped, LineString) else []

    segments = list(trail.geoms)
    segment_lengths = [segment.length for segment in segments]
    total_length = sum(segment_lengths)

    start_distance = start_fraction * total_length
    end_distance = end_fraction * total_length

    pieces: list[LineString] = []
    cumulative = 0.0

    for segment, segment_length in zip(segments, segment_lengths, strict=True):
        segment_start = cumulative
        segment_end = cumulative + segment_length

        # Skip segments entirely outside the requested range
        if segment_end <= start_distance or segment_start >= end_distance:
            cumulative = segment_end
            continue

        clip_start = max(0.0, start_distance - segment_start)
        clip_end = min(segment_length, end_distance - segment_start)

        clipped = substring(segment, clip_start, clip_end)
        if isinstance(clipped, LineString) and len(clipped.coords) >= 2:
            pieces.append(clipped)

        cumulative = segment_end

    return pieces


def _extract_substring(
    trail: LineString | MultiLineString,
    start_fraction: float,
    end_fraction: float,
) -> LineString:
    """Extract geometry between two normalized fractions along the trail.

    Gap portions between non-adjacent segments are skipped, so the result holds
    only real trail coordinates — but consecutive segments end up joined, so
    measure with extract_substring_segments instead of this geometry.
    """
    pieces = extract_substring_segments(trail, start_fraction, end_fraction)

    all_coords: list[tuple[float, ...]] = []
    for piece in pieces:
        coords = list(piece.coords)
        # Deduplicate shared endpoints between adjacent segments
        if all_coords and coords and coords[0] == all_coords[-1]:
            coords = coords[1:]
        all_coords.extend(coords)

    if len(all_coords) < 2:
        return LineString()
    return LineString(all_coords)


def compute_segments_distance_km(segments: Iterable[LineString]) -> float:
    """Total walked distance of several pieces, ignoring the gaps between them."""
    return sum(compute_segment_distance_km(segment) for segment in segments)


def compute_trail_gaps_km(trail: LineString | MultiLineString) -> float:
    """Straight-line distance of the gaps between a trail's mapped segments."""
    if isinstance(trail, LineString):
        return 0.0

    segments = list(trail.geoms)
    total_meters = 0.0
    for previous, following in zip(segments, segments[1:], strict=False):
        previous_longitude, previous_latitude = previous.coords[-1]
        next_longitude, next_latitude = following.coords[0]
        total_meters += haversine_distance(
            latitude_1=previous_latitude,
            longitude_1=previous_longitude,
            latitude_2=next_latitude,
            longitude_2=next_longitude,
        )
    return total_meters / 1000.0


def compute_segment_distance_km(segment: LineString) -> float:
    """Compute the distance of a segment in kilometers using Haversine on consecutive points."""
    coords = list(segment.coords)
    total_meters = 0.0

    for index in range(len(coords) - 1):
        total_meters += haversine_distance(
            latitude_1=coords[index][1],
            longitude_1=coords[index][0],
            latitude_2=coords[index + 1][1],
            longitude_2=coords[index + 1][0],
        )

    return total_meters / 1000.0


def haversine_distance(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Distance in meters between two WGS84 points."""
    phi_1 = math.radians(latitude_1)
    phi_2 = math.radians(latitude_2)
    delta_phi = math.radians(latitude_2 - latitude_1)
    delta_lambda = math.radians(longitude_2 - longitude_1)

    half_chord = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2) ** 2
    )
    return EARTH_RADIUS_METERS * 2 * math.atan2(math.sqrt(half_chord), math.sqrt(1 - half_chord))
