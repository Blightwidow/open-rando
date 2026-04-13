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


MatchedStation = tuple[Station, float, tuple[float, float]]
"""(station, fraction_along_trail, (junction_lon, junction_lat))"""


def match_stations_to_trail(
    stations: list[Station],
    trail: LineString | MultiLineString,
    max_distance_meters: float,
    max_bus_stop_distance_meters: float | None = None,
) -> list[MatchedStation]:
    """Match stations to the trail within max_distance_meters.

    Returns (station, fraction_along_trail, junction_point) triples sorted by
    position along trail. The junction_point is the nearest point on the trail
    as (lon, lat). Supports both LineString and MultiLineString trails.

    When max_bus_stop_distance_meters is provided, bus stops use that tighter
    distance threshold instead of max_distance_meters.
    """
    if isinstance(trail, MultiLineString):
        return _match_stations_multiline(
            stations, trail, max_distance_meters, max_bus_stop_distance_meters
        )

    return _match_stations_single(
        stations, trail, max_distance_meters, max_bus_stop_distance_meters
    )


def _match_stations_single(
    stations: list[Station],
    trail: LineString,
    max_distance_meters: float,
    max_bus_stop_distance_meters: float | None = None,
) -> list[MatchedStation]:
    """Match stations to a single LineString trail."""
    candidates: list[MatchedStation] = []

    for station in stations:
        station_point = Point(station.lon, station.lat)
        nearest_on_trail, _ = nearest_points(trail, station_point)

        raw_distance = station_point.distance(nearest_on_trail)
        distance_meters = degrees_to_meters(raw_distance, station.lat)

        effective_max = max_distance_meters
        if station.transport_type == "bus" and max_bus_stop_distance_meters is not None:
            effective_max = max_bus_stop_distance_meters

        if distance_meters <= effective_max:
            station.distance_to_trail_meters = round(distance_meters, 1)
            fraction_along = trail.project(station_point, normalized=True)
            junction_point = (nearest_on_trail.x, nearest_on_trail.y)
            candidates.append((station, fraction_along, junction_point))
            logger.debug(
                "  %s: %.0fm from trail, position %.3f",
                station.name,
                distance_meters,
                fraction_along,
            )

    candidates.sort(key=lambda pair: pair[1])
    matched = _deduplicate_stations(candidates)

    logger.info("Matched %d stations within %.0fm", len(matched), max_distance_meters)
    for station, fraction, _junction in matched:
        logger.info("  %.3f %s (%.0fm)", fraction, station.name, station.distance_to_trail_meters)

    return matched


def _match_stations_multiline(
    stations: list[Station],
    trail: MultiLineString,
    max_distance_meters: float,
    max_bus_stop_distance_meters: float | None = None,
) -> list[MatchedStation]:
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

    candidates: list[MatchedStation] = []

    for station in stations:
        station_point = Point(station.lon, station.lat)

        # Find the nearest segment and distance
        best_distance_meters = float("inf")
        best_global_fraction = 0.0
        best_junction_point: tuple[float, float] = (0.0, 0.0)

        for segment_index, segment in enumerate(segments):
            nearest_on_segment, _ = nearest_points(segment, station_point)
            raw_distance = station_point.distance(nearest_on_segment)
            distance_meters = degrees_to_meters(raw_distance, station.lat)

            if distance_meters < best_distance_meters:
                best_distance_meters = distance_meters
                best_junction_point = (nearest_on_segment.x, nearest_on_segment.y)
                local_fraction = segment.project(station_point, normalized=True)
                segment_offset = cumulative_offsets[segment_index]
                best_global_fraction = (
                    segment_offset + local_fraction * segment_lengths[segment_index]
                ) / total_length

        effective_max = max_distance_meters
        if station.transport_type == "bus" and max_bus_stop_distance_meters is not None:
            effective_max = max_bus_stop_distance_meters

        if best_distance_meters <= effective_max:
            station.distance_to_trail_meters = round(best_distance_meters, 1)
            candidates.append((station, best_global_fraction, best_junction_point))
            logger.debug(
                "  %s: %.0fm from trail, position %.3f",
                station.name,
                best_distance_meters,
                best_global_fraction,
            )

    candidates.sort(key=lambda pair: pair[1])
    matched = _deduplicate_stations(candidates)

    logger.info("Matched %d stations within %.0fm", len(matched), max_distance_meters)
    for station, fraction, _junction in matched:
        logger.info("  %.3f %s (%.0fm)", fraction, station.name, station.distance_to_trail_meters)

    return matched


def _deduplicate_stations(
    candidates: list[MatchedStation],
) -> list[MatchedStation]:
    """Remove duplicate stations (same name within 500m, or same trail position)."""
    if not candidates:
        return []

    deduplicated: list[MatchedStation] = []

    for station, fraction, junction in candidates:
        is_duplicate = False
        for existing_index, (existing_station, existing_fraction, _existing_junction) in enumerate(
            deduplicated
        ):
            # Same name and close together
            if (
                station.name == existing_station.name
                and abs(fraction - existing_fraction)
                < DEDUPLICATION_DISTANCE_METERS / METERS_PER_DEGREE_LATITUDE
            ):
                # Keep the one closer to the trail
                if station.distance_to_trail_meters < existing_station.distance_to_trail_meters:
                    deduplicated[existing_index] = (station, fraction, junction)
                is_duplicate = True
                break

            # Different name but nearly same position on trail
            if abs(fraction - existing_fraction) < MINIMUM_FRACTION_SEPARATION:
                if station.distance_to_trail_meters < existing_station.distance_to_trail_meters:
                    deduplicated[existing_index] = (station, fraction, junction)
                is_duplicate = True
                break

        if not is_duplicate:
            deduplicated.append((station, fraction, junction))

    return deduplicated
