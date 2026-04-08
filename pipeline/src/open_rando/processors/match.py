from __future__ import annotations

import logging
import math

from shapely.geometry import LineString, Point
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
    trail: LineString,
    max_distance_meters: float,
) -> list[tuple[Station, float]]:
    """Match stations to the trail within max_distance_meters.

    Returns (station, fraction_along_trail) pairs sorted by position along trail.
    """
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
