from __future__ import annotations

from shapely.geometry import LineString

from open_rando.models import Station
from open_rando.processors.match import MatchedStation
from open_rando.processors.slice import find_round_trip_hikes


def _make_station(name: str, lat: float, lon: float) -> Station:
    return Station(name=name, code=name.lower(), lat=lat, lon=lon)


def _matched(station: Station, fraction: float) -> MatchedStation:
    """Create a matched station tuple with junction at station coords (on-trail)."""
    return (station, fraction, (station.lon, station.lat))


def _circular_trail() -> LineString:
    """A small square-ish loop (~4km per side, ~16km circumference)."""
    # Roughly 0.04 degrees ~ 4km at mid-latitudes
    return LineString(
        [
            (2.00, 48.00),
            (2.04, 48.00),
            (2.04, 48.04),
            (2.00, 48.04),
            (2.00, 48.00),  # close the loop
        ]
    )


def _linear_trail() -> LineString:
    """A straight trail that does NOT close."""
    return LineString(
        [
            (2.00, 48.00),
            (2.10, 48.00),
            (2.20, 48.00),
        ]
    )


def test_no_round_trip_on_linear_trail() -> None:
    """Linear trails produce no round-trip hikes."""
    trail = _linear_trail()
    stations = [
        _matched(_make_station("A", 48.00, 2.00), 0.0),
        _matched(_make_station("B", 48.00, 2.05), 0.5),
        _matched(_make_station("C", 48.00, 2.10), 1.0),
    ]
    result = find_round_trip_hikes(
        trail, stations, min_step_distance_km=4.0, max_step_distance_km=20.0
    )
    assert result == []


def test_no_round_trip_with_fewer_than_two_stations() -> None:
    """Single-station trails return empty."""
    trail = _circular_trail()
    stations = [
        _matched(_make_station("A", 48.00, 2.00), 0.0),
    ]
    result = find_round_trip_hikes(
        trail, stations, min_step_distance_km=4.0, max_step_distance_km=20.0
    )
    assert result == []


def test_round_trip_returns_loop_on_circular_trail() -> None:
    """Circular trail with well-spaced stations yields a loop hike."""
    trail = _circular_trail()
    # Place four stations roughly evenly around the loop
    stations = [
        _matched(_make_station("A", 48.00, 2.00), 0.00),
        _matched(_make_station("B", 48.00, 2.04), 0.25),
        _matched(_make_station("C", 48.04, 2.04), 0.50),
        _matched(_make_station("D", 48.04, 2.00), 0.75),
    ]
    result = find_round_trip_hikes(
        trail, stations, min_step_distance_km=2.0, max_step_distance_km=8.0
    )
    assert len(result) == 1, "Expected exactly one round-trip hike"


def test_round_trip_first_and_last_station_are_same() -> None:
    """The loop must start and end at the same station."""
    trail = _circular_trail()
    stations = [
        _matched(_make_station("A", 48.00, 2.00), 0.00),
        _matched(_make_station("B", 48.00, 2.04), 0.25),
        _matched(_make_station("C", 48.04, 2.04), 0.50),
        _matched(_make_station("D", 48.04, 2.00), 0.75),
    ]
    result = find_round_trip_hikes(
        trail, stations, min_step_distance_km=2.0, max_step_distance_km=8.0
    )
    assert len(result) == 1
    hike_steps = result[0]
    first_station = hike_steps[0][0]  # start of first step
    last_station = hike_steps[-1][1]  # end of last step (wrap-around)
    assert first_station.code == last_station.code, (
        f"Expected loop start==end, got {first_station.name} != {last_station.name}"
    )


def test_wrap_geometry_is_valid_linestring() -> None:
    """The wrap-around step geometry must be a non-degenerate LineString."""
    trail = _circular_trail()
    stations = [
        _matched(_make_station("A", 48.00, 2.00), 0.00),
        _matched(_make_station("B", 48.00, 2.04), 0.25),
        _matched(_make_station("C", 48.04, 2.04), 0.50),
        _matched(_make_station("D", 48.04, 2.00), 0.75),
    ]
    result = find_round_trip_hikes(
        trail, stations, min_step_distance_km=2.0, max_step_distance_km=8.0
    )
    assert len(result) == 1
    hike_steps = result[0]
    wrap_step = hike_steps[-1]
    wrap_geometry = wrap_step[2]
    assert isinstance(wrap_geometry, LineString)
    assert not wrap_geometry.is_empty
    coords = list(wrap_geometry.coords)
    assert len(coords) >= 2
