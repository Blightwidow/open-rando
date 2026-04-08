from __future__ import annotations

import math

from shapely.geometry import LineString
from shapely.ops import substring

from open_rando.models import Station

MINIMUM_SEGMENT_DISTANCE_KM = 0.5
EARTH_RADIUS_METERS = 6_371_000


def slice_segments(
    trail: LineString,
    matched_stations: list[tuple[Station, float]],
) -> list[tuple[Station, Station, LineString]]:
    """Slice the trail into segments between consecutive station pairs.

    matched_stations must be sorted by fraction_along_trail.
    Returns (start_station, end_station, segment_linestring) triples.
    """
    trail_length = trail.length
    segments: list[tuple[Station, Station, LineString]] = []

    for index in range(len(matched_stations) - 1):
        start_station, start_fraction = matched_stations[index]
        end_station, end_fraction = matched_stations[index + 1]

        start_distance = start_fraction * trail_length
        end_distance = end_fraction * trail_length

        segment = substring(trail, start_distance, end_distance)

        if segment.is_empty or segment.length == 0:
            continue

        distance_km = compute_segment_distance_km(segment)
        if distance_km < MINIMUM_SEGMENT_DISTANCE_KM:
            continue

        segments.append((start_station, end_station, segment))

    return segments


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
