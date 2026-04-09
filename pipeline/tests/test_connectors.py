from __future__ import annotations

from unittest.mock import patch

from shapely.geometry import LineString

from open_rando.models import Station
from open_rando.processors.connectors import _concatenate_geometries, attach_connectors
from open_rando.processors.match import MatchedStation


def _make_station(name: str, lat: float, lon: float, distance_to_trail: float = 0.0) -> Station:
    station = Station(name=name, code=name.lower(), lat=lat, lon=lon)
    station.distance_to_trail_meters = distance_to_trail
    return station


def _matched(
    station: Station, fraction: float, junction_lon: float, junction_lat: float
) -> MatchedStation:
    return (station, fraction, (junction_lon, junction_lat))


def test_concatenate_with_both_connectors() -> None:
    """Full assembly: start_connector + trail + end_connector."""
    start = LineString([(0, 0), (1, 0), (2, 0)])
    trail = LineString([(2, 0), (3, 0), (4, 0)])
    end = LineString([(4, 0), (5, 0), (6, 0)])

    result = _concatenate_geometries(start, trail, end)
    coords = list(result.coords)
    assert coords == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0)]


def test_concatenate_with_no_connectors() -> None:
    """No connectors — returns the trail segment unchanged."""
    trail = LineString([(2, 0), (3, 0), (4, 0)])
    result = _concatenate_geometries(None, trail, None)
    assert list(result.coords) == list(trail.coords)


def test_concatenate_with_only_start_connector() -> None:
    start = LineString([(0, 0), (1, 0), (2, 0)])
    trail = LineString([(2, 0), (3, 0), (4, 0)])
    result = _concatenate_geometries(start, trail, None)
    coords = list(result.coords)
    assert coords == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]


def test_concatenate_with_only_end_connector() -> None:
    trail = LineString([(2, 0), (3, 0), (4, 0)])
    end = LineString([(4, 0), (5, 0), (6, 0)])
    result = _concatenate_geometries(None, trail, end)
    coords = list(result.coords)
    assert coords == [(2, 0), (3, 0), (4, 0), (5, 0), (6, 0)]


def test_skip_connector_below_threshold() -> None:
    """Stations closer than threshold get no connector."""
    station_a = _make_station("A", 48.00, 2.00, distance_to_trail=50.0)
    station_b = _make_station("B", 48.01, 2.10, distance_to_trail=50.0)
    trail_segment = LineString([(2.00, 48.00), (2.05, 48.005), (2.10, 48.01)])

    raw_steps = [(station_a, station_b, trail_segment, 10.0)]
    matched = [
        _matched(station_a, 0.0, 2.00, 48.00),
        _matched(station_b, 1.0, 2.10, 48.01),
    ]

    enriched, all_cached = attach_connectors(raw_steps, matched, connector_threshold_meters=100.0)
    assert len(enriched) == 1
    assert all_cached is True
    # Geometry unchanged — no connectors added
    assert list(enriched[0][2].coords) == list(trail_segment.coords)
    # Distance unchanged
    assert enriched[0][3] == 10.0


def test_attach_connectors_with_osrm_fallback() -> None:
    """When OSRM returns None, falls back to straight line."""
    station_a = _make_station("A", 48.00, 2.00, distance_to_trail=500.0)
    station_b = _make_station("B", 48.01, 2.10, distance_to_trail=500.0)
    trail_segment = LineString([(2.001, 48.001), (2.05, 48.005), (2.099, 48.009)])

    raw_steps = [(station_a, station_b, trail_segment, 10.0)]
    matched = [
        _matched(station_a, 0.0, 2.001, 48.001),
        _matched(station_b, 1.0, 2.099, 48.009),
    ]

    with patch(
        "open_rando.processors.connectors.fetch_pedestrian_route",
        return_value=(None, 0.0, False),
    ):
        enriched, _all_cached = attach_connectors(
            raw_steps, matched, connector_threshold_meters=100.0
        )

    assert len(enriched) == 1
    result_coords = list(enriched[0][2].coords)
    # Should start at station A and end at station B
    assert result_coords[0] == (2.00, 48.00)
    assert result_coords[-1] == (2.10, 48.01)
    # Distance should be greater than trail-only distance
    assert enriched[0][3] > 10.0


def test_attach_connectors_with_osrm_success() -> None:
    """When OSRM returns a route, it is used as connector."""
    station_a = _make_station("A", 48.00, 2.00, distance_to_trail=500.0)
    station_b = _make_station("B", 48.01, 2.10, distance_to_trail=30.0)  # below threshold
    trail_segment = LineString([(2.005, 48.002), (2.05, 48.005), (2.10, 48.01)])

    raw_steps = [(station_a, station_b, trail_segment, 10.0)]
    matched = [
        _matched(station_a, 0.0, 2.005, 48.002),
        _matched(station_b, 1.0, 2.10, 48.01),
    ]

    osrm_route = LineString([(2.00, 48.00), (2.003, 48.001), (2.005, 48.002)])

    def mock_fetch(origin_lat, origin_lon, destination_lat, destination_lon):
        return osrm_route, 0.5, False

    with patch(
        "open_rando.processors.connectors.fetch_pedestrian_route",
        side_effect=mock_fetch,
    ):
        enriched, _all_cached = attach_connectors(
            raw_steps, matched, connector_threshold_meters=100.0
        )

    assert len(enriched) == 1
    result_coords = list(enriched[0][2].coords)
    # Should start with OSRM route coords (minus last) then trail
    assert result_coords[0] == (2.00, 48.00)
    assert result_coords[1] == (2.003, 48.001)
    # No end connector (station B below threshold), so ends at trail end
    assert result_coords[-1] == (2.10, 48.01)
    # Distance includes connector
    assert enriched[0][3] == 10.5
