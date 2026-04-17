from __future__ import annotations

import logging
import math

from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import nearest_points

from open_rando.fetchers.routing import fetch_pedestrian_distance_matrix
from open_rando.models import Station

logger = logging.getLogger("open_rando")

METERS_PER_DEGREE_LATITUDE = 111_320.0
DEDUPLICATION_DISTANCE_METERS = 500.0
MINIMUM_FRACTION_SEPARATION = 0.001
NEAREST_STATION_RADIUS_METERS = 5000.0
WALKING_REFINEMENT_SAMPLE_STEP_METERS = 150.0
WALKING_REFINEMENT_RADIUS_METERS = 5000.0
EARTH_RADIUS_METERS = 6_371_000


def degrees_to_meters(distance_degrees: float, latitude: float) -> float:
    """Approximate conversion from degrees to meters at a given latitude."""
    meters_per_degree_longitude = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(latitude))
    average_scale = (METERS_PER_DEGREE_LATITUDE + meters_per_degree_longitude) / 2
    return distance_degrees * average_scale


def _haversine_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Great-circle distance in meters between two WGS84 points."""
    phi_a = math.radians(latitude_a)
    phi_b = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    half_chord = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return EARTH_RADIUS_METERS * 2 * math.atan2(math.sqrt(half_chord), math.sqrt(1 - half_chord))


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
    matched = _filter_never_closest_stations(matched, trail)

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
    matched = _filter_never_closest_stations(matched, trail)

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


def _filter_never_closest_stations(
    candidates: list[MatchedStation],
    trail: LineString | MultiLineString,
) -> list[MatchedStation]:
    """Remove stations that are never the closest to any trail point within range.

    For each trail vertex within NEAREST_STATION_RADIUS_METERS of at least one
    station, determine which station is closest. Stations that are never the
    closest to any trail point are removed.
    """
    if len(candidates) <= 1:
        return candidates

    trail_coords: list[tuple[float, float]] = []
    if isinstance(trail, MultiLineString):
        for segment in trail.geoms:
            trail_coords.extend((coordinate[0], coordinate[1]) for coordinate in segment.coords)
    else:
        trail_coords.extend((coordinate[0], coordinate[1]) for coordinate in trail.coords)

    station_positions = [(station.lon, station.lat) for station, _fraction, _junction in candidates]

    closest_set: set[int] = set()

    for trail_lon, trail_lat in trail_coords:
        best_index = -1
        best_distance_squared = float("inf")
        within_radius = False

        for station_index, (station_lon, station_lat) in enumerate(station_positions):
            delta_lon = trail_lon - station_lon
            delta_lat = trail_lat - station_lat
            distance_squared = delta_lon * delta_lon + delta_lat * delta_lat

            if distance_squared < best_distance_squared:
                best_distance_squared = distance_squared
                best_index = station_index

        if best_index >= 0:
            best_distance_meters = degrees_to_meters(best_distance_squared**0.5, trail_lat)
            if best_distance_meters <= NEAREST_STATION_RADIUS_METERS:
                within_radius = True

        if within_radius:
            closest_set.add(best_index)

    result = [candidate for index, candidate in enumerate(candidates) if index in closest_set]

    removed_count = len(candidates) - len(result)
    if removed_count > 0:
        removed_names = [
            candidates[index][0].name
            for index in range(len(candidates))
            if index not in closest_set
        ]
        logger.info(
            "Nearest-station filtering removed %d station(s): %s",
            removed_count,
            ", ".join(removed_names),
        )

    return result


def _sample_trail(
    trail: LineString | MultiLineString,
    step_meters: float = WALKING_REFINEMENT_SAMPLE_STEP_METERS,
) -> list[tuple[float, tuple[float, float]]]:
    """Sample the trail at regular along-arc intervals.

    Returns (global_fraction_along_trail, (longitude, latitude)) pairs. The fraction
    is based on cumulative haversine arc length so it matches the metric used for
    reporting section distances. Supports LineString and MultiLineString (segments
    are treated as contiguous, matching the existing global-fraction semantics).
    """
    segments = list(trail.geoms) if isinstance(trail, MultiLineString) else [trail]

    vertices: list[tuple[float, float, float]] = []
    cumulative_meters = 0.0
    for segment in segments:
        segment_coords = list(segment.coords)
        if not segment_coords:
            continue
        for vertex_index, vertex in enumerate(segment_coords):
            longitude = float(vertex[0])
            latitude = float(vertex[1])
            if not vertices:
                vertices.append((longitude, latitude, 0.0))
                continue
            if vertex_index == 0:
                vertices.append((longitude, latitude, cumulative_meters))
                continue
            previous_longitude, previous_latitude, previous_cumulative = vertices[-1]
            step_distance = _haversine_meters(
                previous_latitude, previous_longitude, latitude, longitude
            )
            cumulative_meters = previous_cumulative + step_distance
            vertices.append((longitude, latitude, cumulative_meters))

    if len(vertices) < 2:
        return []
    total_length_meters = vertices[-1][2]
    if total_length_meters <= 0:
        return []

    samples: list[tuple[float, tuple[float, float]]] = []
    next_target_meters = 0.0
    vertex_cursor = 0
    while vertex_cursor < len(vertices) - 1 and next_target_meters <= total_length_meters:
        start_vertex = vertices[vertex_cursor]
        end_vertex = vertices[vertex_cursor + 1]
        if next_target_meters > end_vertex[2]:
            vertex_cursor += 1
            continue
        piece_length = end_vertex[2] - start_vertex[2]
        if piece_length <= 0:
            vertex_cursor += 1
            continue
        interpolation = (next_target_meters - start_vertex[2]) / piece_length
        longitude = start_vertex[0] + interpolation * (end_vertex[0] - start_vertex[0])
        latitude = start_vertex[1] + interpolation * (end_vertex[1] - start_vertex[1])
        samples.append((next_target_meters / total_length_meters, (longitude, latitude)))
        next_target_meters += step_meters

    last_vertex = vertices[-1]
    if not samples or samples[-1][0] < 1.0 - 1e-9:
        samples.append((1.0, (last_vertex[0], last_vertex[1])))

    return samples


def refine_junctions_by_walking_distance(
    matched: list[MatchedStation],
    trail: LineString | MultiLineString,
    radius_meters: float = WALKING_REFINEMENT_RADIUS_METERS,
    step_meters: float = WALKING_REFINEMENT_SAMPLE_STEP_METERS,
) -> list[MatchedStation]:
    """Re-pick each station's junction point to minimize actual walking distance.

    For each matched station, gathers trail samples within radius_meters crow-fly,
    queries OSRM foot routing (table API) for walking distance from the station to
    each candidate, and replaces the junction with the minimum-walking-distance
    sample. Falls back to the original junction when OSRM fails or no candidate is
    reachable. The station's `distance_to_trail_meters` is updated to the actual
    walking distance when refinement succeeds.
    """
    if not matched:
        return matched

    samples = _sample_trail(trail, step_meters=step_meters)
    if not samples:
        return matched

    refined: list[MatchedStation] = []
    for station, original_fraction, original_junction in matched:
        candidate_indices: list[int] = []
        for sample_index, (_sample_fraction, sample_point) in enumerate(samples):
            sample_longitude, sample_latitude = sample_point
            crow_fly_meters = _haversine_meters(
                station.lat, station.lon, sample_latitude, sample_longitude
            )
            if crow_fly_meters <= radius_meters:
                candidate_indices.append(sample_index)

        if not candidate_indices:
            refined.append((station, original_fraction, original_junction))
            continue

        destination_latlons = [
            (samples[sample_index][1][1], samples[sample_index][1][0])
            for sample_index in candidate_indices
        ]
        walking_distances = fetch_pedestrian_distance_matrix(
            (station.lat, station.lon),
            destination_latlons,
        )

        best_candidate_position = -1
        best_walking_meters = float("inf")
        for candidate_position, walking_meters in enumerate(walking_distances):
            if walking_meters is None:
                continue
            if walking_meters < best_walking_meters:
                best_walking_meters = walking_meters
                best_candidate_position = candidate_position

        if best_candidate_position < 0:
            logger.warning(
                "No reachable trail point for %s; keeping perpendicular junction",
                station.name,
            )
            refined.append((station, original_fraction, original_junction))
            continue

        best_sample_index = candidate_indices[best_candidate_position]
        new_fraction, new_junction = samples[best_sample_index]
        previous_distance_meters = station.distance_to_trail_meters
        station.distance_to_trail_meters = round(best_walking_meters, 1)
        logger.info(
            "Refined %s: fraction %.3f -> %.3f, distance %.0fm -> %.0fm (walking)",
            station.name,
            original_fraction,
            new_fraction,
            previous_distance_meters,
            best_walking_meters,
        )
        refined.append((station, new_fraction, new_junction))

    refined.sort(key=lambda item: item[1])
    return _deduplicate_stations(refined)
