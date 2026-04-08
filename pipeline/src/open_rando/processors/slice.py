from __future__ import annotations

import math

from shapely.geometry import LineString
from shapely.ops import substring

from open_rando.models import Station

MINIMUM_SEGMENT_DISTANCE_KM = 0.5
EARTH_RADIUS_METERS = 6_371_000


def find_hikes(
    trail: LineString,
    matched_stations: list[tuple[Station, float]],
    min_step_distance_km: float,
    max_step_distance_km: float,
) -> list[list[tuple[Station, Station, LineString, float]]]:
    """Find multi-step hikes where each step is within the distance range.

    matched_stations must be sorted by fraction_along_trail.
    Returns list of hikes. Each hike is a list of steps:
    (start_station, end_station, geometry, distance_km).
    """
    trail_length = trail.length
    station_count = len(matched_stations)

    cumulative_km = _compute_cumulative_distances(trail, matched_stations)

    adjacency = _build_step_graph(
        cumulative_km, station_count, min_step_distance_km, max_step_distance_km
    )

    maximal_paths = _find_maximal_paths(adjacency, station_count)

    hikes: list[list[tuple[Station, Station, LineString, float]]] = []
    for path in maximal_paths:
        steps: list[tuple[Station, Station, LineString, float]] = []
        for step_index in range(len(path) - 1):
            source = path[step_index]
            target = path[step_index + 1]
            start_station = matched_stations[source][0]
            end_station = matched_stations[target][0]
            start_distance = matched_stations[source][1] * trail_length
            end_distance = matched_stations[target][1] * trail_length
            geometry = substring(trail, start_distance, end_distance)
            distance_km = round(cumulative_km[target] - cumulative_km[source], 1)
            steps.append((start_station, end_station, geometry, distance_km))
        hikes.append(steps)

    return hikes


def _compute_cumulative_distances(
    trail: LineString,
    matched_stations: list[tuple[Station, float]],
) -> list[float]:
    """Compute cumulative haversine distances along the trail for each station."""
    trail_length = trail.length
    cumulative_km: list[float] = [0.0]

    for index in range(1, len(matched_stations)):
        previous_fraction = matched_stations[index - 1][1]
        current_fraction = matched_stations[index][1]
        segment = substring(
            trail,
            previous_fraction * trail_length,
            current_fraction * trail_length,
        )
        segment_distance = compute_segment_distance_km(segment)
        cumulative_km.append(cumulative_km[-1] + segment_distance)

    return cumulative_km


def _build_step_graph(
    cumulative_km: list[float],
    station_count: int,
    min_step_distance_km: float,
    max_step_distance_km: float,
) -> dict[int, list[int]]:
    """Build adjacency list: station_index -> reachable station indices within distance range."""
    adjacency: dict[int, list[int]] = {index: [] for index in range(station_count)}

    for source in range(station_count):
        for target in range(source + 1, station_count):
            step_distance = cumulative_km[target] - cumulative_km[source]
            if step_distance > max_step_distance_km:
                break
            if step_distance >= min_step_distance_km:
                adjacency[source].append(target)

    return adjacency


def _find_maximal_paths(
    adjacency: dict[int, list[int]],
    station_count: int,
) -> list[list[int]]:
    """Find all maximal paths via DFS. A path is maximal if it cannot be extended forward."""
    all_paths: list[list[int]] = []

    def depth_first_search(path: list[int]) -> None:
        last = path[-1]
        extended = False
        for next_index in adjacency[last]:
            extended = True
            path.append(next_index)
            depth_first_search(path)
            path.pop()
        if not extended and len(path) >= 2:
            all_paths.append(path[:])

    for start_index in range(station_count):
        if adjacency[start_index]:
            depth_first_search([start_index])

    return _remove_subpaths(all_paths)


def _remove_subpaths(paths: list[list[int]]) -> list[list[int]]:
    """Remove paths that are contiguous sub-sequences of longer paths."""
    paths.sort(key=len, reverse=True)
    kept: list[list[int]] = []

    for path in paths:
        is_subpath = False
        path_tuple = tuple(path)
        for longer in kept:
            longer_tuple = tuple(longer)
            window_size = len(path_tuple)
            for offset in range(len(longer_tuple) - window_size + 1):
                if longer_tuple[offset : offset + window_size] == path_tuple:
                    is_subpath = True
                    break
            if is_subpath:
                break
        if not is_subpath:
            kept.append(path)

    return kept


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
