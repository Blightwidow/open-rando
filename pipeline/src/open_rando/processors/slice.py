from __future__ import annotations

import logging
import math
from collections import defaultdict

from shapely.geometry import LineString, MultiLineString
from shapely.ops import substring

from open_rando.models import Station

logger = logging.getLogger("open_rando")

MINIMUM_SEGMENT_DISTANCE_KM = 0.5
EARTH_RADIUS_METERS = 6_371_000


def _flatten_to_linestring(trail: LineString | MultiLineString) -> LineString:
    """Convert MultiLineString to single LineString by connecting segments.

    For the slicer, this is acceptable since stations are already matched to real
    trail positions. Gap portions become straight-line jumps.
    """
    if isinstance(trail, LineString):
        return trail

    all_coords: list[tuple[float, float]] = []
    for segment in trail.geoms:
        coords = list(segment.coords)
        if all_coords and coords[0] != all_coords[-1]:
            pass  # gap jump — just concatenate
        if all_coords and coords[0] == all_coords[-1]:
            coords = coords[1:]
        all_coords.extend(coords)

    return LineString(all_coords)


def find_hikes(
    trail: LineString | MultiLineString,
    matched_stations: list[tuple[Station, float]],
    min_step_distance_km: float,
    max_step_distance_km: float,
) -> list[list[tuple[Station, Station, LineString, float]]]:
    """Find multi-step hikes where each step is within the distance range.

    matched_stations must be sorted by fraction_along_trail.
    Returns list of hikes. Each hike is a list of steps:
    (start_station, end_station, geometry, distance_km).
    Supports both LineString and MultiLineString trails.
    """
    flat_trail = _flatten_to_linestring(trail)
    trail_length = flat_trail.length
    station_count = len(matched_stations)

    cumulative_km = _compute_cumulative_distances(flat_trail, matched_stations)

    adjacency = _build_step_graph(
        cumulative_km, station_count, min_step_distance_km, max_step_distance_km
    )

    maximal_paths = _find_longest_paths(adjacency, cumulative_km, station_count)

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
            geometry = substring(flat_trail, start_distance, end_distance)
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


def _find_longest_paths(
    adjacency: dict[int, list[int]],
    cumulative_km: list[float],
    station_count: int,
) -> list[list[int]]:
    """Find the single longest path (by trail distance) per connected component.

    The step graph is a DAG with edges only going from lower to higher station indices,
    so longest-path DP runs in O(V+E) via topological order (ascending index).
    Returns one path per connected component of the graph.
    """
    components = _find_connected_components(adjacency, station_count)
    longest_paths: list[list[int]] = []

    for component in components:
        if len(component) < 2:
            continue

        best_distance: dict[int, float] = {station: 0.0 for station in component}
        predecessor: dict[int, int | None] = {station: None for station in component}

        for station in sorted(component):
            for neighbor in adjacency[station]:
                if neighbor not in best_distance:
                    continue
                candidate = best_distance[station] + (
                    cumulative_km[neighbor] - cumulative_km[station]
                )
                if candidate > best_distance[neighbor]:
                    best_distance[neighbor] = candidate
                    predecessor[neighbor] = station

        end_station = max(component, key=lambda station: best_distance[station])
        if best_distance[end_station] == 0.0:
            continue

        path: list[int] = []
        current: int | None = end_station
        while current is not None:
            path.append(current)
            current = predecessor[current]
        path.reverse()

        if len(path) >= 2:
            longest_paths.append(path)

    return longest_paths


def _find_connected_components(
    adjacency: dict[int, list[int]],
    station_count: int,
) -> list[set[int]]:
    """Find connected components of the step graph (treating edges as undirected)."""
    undirected: dict[int, set[int]] = defaultdict(set)
    for source, targets in adjacency.items():
        for target in targets:
            undirected[source].add(target)
            undirected[target].add(source)

    visited: set[int] = set()
    components: list[set[int]] = []

    for station in range(station_count):
        if station in visited or station not in undirected:
            continue
        component: set[int] = set()
        queue = [station]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            for neighbor in undirected[current]:
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(component)

    return components


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
