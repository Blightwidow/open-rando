from __future__ import annotations

import logging

from shapely.geometry import LineString

from open_rando.fetchers.routing import fetch_pedestrian_route, make_straight_line_connector
from open_rando.models import Station
from open_rando.processors.match import MatchedStation

logger = logging.getLogger("open_rando")


def attach_connectors(
    raw_steps: list[tuple[Station, Station, LineString, float]],
    matched_stations: list[MatchedStation],
    connector_threshold_meters: float,
) -> tuple[list[tuple[Station, Station, LineString, float]], bool]:
    """Attach pedestrian connector paths between stations and the trail.

    For each step, prepends a walking route from the start station to its trail
    junction, and appends a walking route from the trail junction to the end station.

    Returns (enriched_steps, all_cached).
    """
    junction_by_code: dict[str, tuple[float, float]] = {}
    distance_by_code: dict[str, float] = {}
    for station, _fraction, junction_point in matched_stations:
        junction_by_code[station.code] = junction_point
        distance_by_code[station.code] = station.distance_to_trail_meters

    # Cache connector routes per station code to avoid duplicate OSRM calls
    # Key: (station_code, direction) where direction is "to_trail" or "from_trail"
    connector_cache: dict[tuple[str, str], tuple[LineString | None, float]] = {}
    all_cached = True

    enriched_steps: list[tuple[Station, Station, LineString, float]] = []

    for start_station, end_station, trail_segment, trail_distance_km in raw_steps:
        start_connector, start_connector_km, start_cached = _get_connector(
            station=start_station,
            junction_point=junction_by_code[start_station.code],
            distance_to_trail=distance_by_code[start_station.code],
            threshold_meters=connector_threshold_meters,
            direction="to_trail",
            connector_cache=connector_cache,
        )
        end_connector, end_connector_km, end_cached = _get_connector(
            station=end_station,
            junction_point=junction_by_code[end_station.code],
            distance_to_trail=distance_by_code[end_station.code],
            threshold_meters=connector_threshold_meters,
            direction="from_trail",
            connector_cache=connector_cache,
        )

        if not start_cached or not end_cached:
            all_cached = False

        combined_geometry = _concatenate_geometries(start_connector, trail_segment, end_connector)
        total_distance_km = round(start_connector_km + trail_distance_km + end_connector_km, 1)

        enriched_steps.append((start_station, end_station, combined_geometry, total_distance_km))

    return enriched_steps, all_cached


def _get_connector(
    station: Station,
    junction_point: tuple[float, float],
    distance_to_trail: float,
    threshold_meters: float,
    direction: str,
    connector_cache: dict[tuple[str, str], tuple[LineString | None, float]],
) -> tuple[LineString | None, float, bool]:
    """Get a connector route for a station, using cache when available.

    direction is "to_trail" (station -> junction) or "from_trail" (junction -> station).
    Returns (geometry, distance_km, was_cached).
    """
    if distance_to_trail < threshold_meters:
        return None, 0.0, True

    cache_key = (station.code, direction)
    if cache_key in connector_cache:
        geometry, distance_km = connector_cache[cache_key]
        return geometry, distance_km, True

    junction_lon, junction_lat = junction_point

    if direction == "to_trail":
        origin_lat, origin_lon = station.lat, station.lon
        destination_lat, destination_lon = junction_lat, junction_lon
    else:
        origin_lat, origin_lon = junction_lat, junction_lon
        destination_lat, destination_lon = station.lat, station.lon

    geometry, distance_km, osrm_cached = fetch_pedestrian_route(
        origin_lat, origin_lon, destination_lat, destination_lon
    )

    if geometry is None:
        logger.info(
            "  OSRM fallback for %s (%s), using straight line",
            station.name,
            direction,
        )
        geometry, distance_km = make_straight_line_connector(
            origin_lat, origin_lon, destination_lat, destination_lon
        )

    connector_cache[cache_key] = (geometry, distance_km)

    return geometry, distance_km, osrm_cached


def _concatenate_geometries(
    start_connector: LineString | None,
    trail_segment: LineString,
    end_connector: LineString | None,
) -> LineString:
    """Concatenate connector and trail geometries into a single LineString.

    Ensures coordinate continuity by using the trail segment endpoints at join points
    (drops the last coord of start_connector and first coord of end_connector).
    """
    coords: list[tuple[float, ...]] = []

    if start_connector is not None:
        connector_coords = list(start_connector.coords)
        # Drop last coord of connector — use the trail segment's first coord instead
        coords.extend(connector_coords[:-1])

    coords.extend(trail_segment.coords)

    if end_connector is not None:
        connector_coords = list(end_connector.coords)
        # Drop first coord of connector — trail segment's last coord is already there
        coords.extend(connector_coords[1:])

    return LineString(coords)
