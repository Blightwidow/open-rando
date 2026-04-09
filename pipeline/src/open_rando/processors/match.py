from __future__ import annotations

import logging
import math

from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import nearest_points

from open_rando.models import Station

logger = logging.getLogger("open_rando")

METERS_PER_DEGREE_LATITUDE = 111_320.0
DEDUPLICATION_DISTANCE_METERS = 500.0
MINIMUM_FRACTION_SEPARATION = 0.001


def degrees_to_meters(distance_degrees: float, latitude: float) -> float:
    """Approximate conversion from degrees to meters at a given latitude."""
    meters_per_degree_longitude = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(latitude))
    average_scale = (METERS_PER_DEGREE_LATITUDE + meters_per_degree_longitude) / 2
    return distance_degrees * average_scale


def match_stations_to_trail(
    stations: list[Station],
    trail: LineString | MultiLineString,
    max_distance_meters: float,
) -> list[tuple[Station, float]]:
    """Match stations to the trail within max_distance_meters.

    Returns (station, fraction_along_trail) pairs sorted by position along trail.
    Supports both LineString and MultiLineString trails. For MultiLineString, fractions
    are computed as global position across all segments weighted by segment length.
    """
    if isinstance(trail, MultiLineString):
        return _match_stations_multiline(stations, trail, max_distance_meters)

    return _match_stations_single(stations, trail, max_distance_meters)


def _match_stations_single(
    stations: list[Station],
    trail: LineString,
    max_distance_meters: float,
) -> list[tuple[Station, float]]:
    """Match stations to a single LineString trail."""
    candidates: list[tuple[Station, float]] = []

    for station in stations:
        station_point = Point(station.lon, station.lat)
        nearest_on_trail, _ = nearest_points(trail, station_point)

        raw_distance = station_point.distance(nearest_on_trail)
        distance_meters = degrees_to_meters(raw_distance, station.lat)

        if distance_meters <= max_distance_meters:
            station.distance_to_trail_meters = round(distance_meters, 1)
            fraction_along = trail.project(station_point, normalized=True)
            candidates.append((station, fraction_along))
            logger.debug(
                "  %s: %.0fm from trail, position %.3f",
                station.name,
                distance_meters,
                fraction_along,
            )

    candidates.sort(key=lambda pair: pair[1])
    matched = _deduplicate_stations(candidates)

    logger.info("Matched %d stations within %.0fm", len(matched), max_distance_meters)
    for station, fraction in matched:
        logger.info("  %.3f %s (%.0fm)", fraction, station.name, station.distance_to_trail_meters)

    return matched


def _match_stations_multiline(
    stations: list[Station],
    trail: MultiLineString,
    max_distance_meters: float,
) -> list[tuple[Station, float]]:
    """Match stations to a MultiLineString trail using global fractions."""
    segments = list(trail.geoms)
    segment_lengths = [segment.length for segment in segments]
    total_length = sum(segment_lengths)

    if total_length == 0:
        return []

    # Compute cumulative length offsets for each segment
    cumulative_offsets = [0.0]
    for length in segment_lengths:
        cumulative_offsets.append(cumulative_offsets[-1] + length)

    candidates: list[tuple[Station, float]] = []

    for station in stations:
        station_point = Point(station.lon, station.lat)

        # Find the nearest segment and distance
        best_distance_meters = float("inf")
        best_global_fraction = 0.0

        for segment_index, segment in enumerate(segments):
            nearest_on_segment, _ = nearest_points(segment, station_point)
            raw_distance = station_point.distance(nearest_on_segment)
            distance_meters = degrees_to_meters(raw_distance, station.lat)

            if distance_meters < best_distance_meters:
                best_distance_meters = distance_meters
                local_fraction = segment.project(station_point, normalized=True)
                segment_offset = cumulative_offsets[segment_index]
                best_global_fraction = (
                    segment_offset + local_fraction * segment_lengths[segment_index]
                ) / total_length

        if best_distance_meters <= max_distance_meters:
            station.distance_to_trail_meters = round(best_distance_meters, 1)
            candidates.append((station, best_global_fraction))
            logger.debug(
                "  %s: %.0fm from trail, position %.3f",
                station.name,
                best_distance_meters,
                best_global_fraction,
            )

    candidates.sort(key=lambda pair: pair[1])
    matched = _deduplicate_stations(candidates)

    logger.info("Matched %d stations within %.0fm", len(matched), max_distance_meters)
    for station, fraction in matched:
        logger.info("  %.3f %s (%.0fm)", fraction, station.name, station.distance_to_trail_meters)

    return matched


def _deduplicate_stations(
    candidates: list[tuple[Station, float]],
) -> list[tuple[Station, float]]:
    """Remove duplicate stations (same name within 500m, or same trail position)."""
    if not candidates:
        return []

    deduplicated: list[tuple[Station, float]] = []

    for station, fraction in candidates:
        is_duplicate = False
        for existing_index, (existing_station, existing_fraction) in enumerate(deduplicated):
            # Same name and close together
            if (
                station.name == existing_station.name
                and abs(fraction - existing_fraction)
                < DEDUPLICATION_DISTANCE_METERS / METERS_PER_DEGREE_LATITUDE
            ):
                # Keep the one closer to the trail
                if station.distance_to_trail_meters < existing_station.distance_to_trail_meters:
                    deduplicated[existing_index] = (station, fraction)
                is_duplicate = True
                break

            # Different name but nearly same position on trail
            if abs(fraction - existing_fraction) < MINIMUM_FRACTION_SEPARATION:
                if station.distance_to_trail_meters < existing_station.distance_to_trail_meters:
                    deduplicated[existing_index] = (station, fraction)
                is_duplicate = True
                break

        if not is_duplicate:
            deduplicated.append((station, fraction))

    return deduplicated
