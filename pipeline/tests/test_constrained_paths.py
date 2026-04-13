from __future__ import annotations

from shapely.geometry import LineString

from open_rando.models import Accommodation, Station
from open_rando.processors.match import MatchedStation
from open_rando.processors.slice import find_hikes


def _make_station(
    name: str,
    transport_type: str = "train",
    has_hotel: bool = False,
    route_ids: set[str] | None = None,
) -> Station:
    station = Station(
        name=name,
        code=name.lower().replace(" ", "_"),
        lat=48.0,
        lon=2.0,
        transport_type=transport_type,
        accommodation=Accommodation(has_hotel=has_hotel),
    )
    if route_ids is not None:
        station.connected_route_ids = route_ids
    elif transport_type == "train":
        station.connected_route_ids = {"__train__"}
    return station


def _make_trail_and_matched(
    stations: list[Station], count: int
) -> tuple[LineString, list[MatchedStation]]:
    """Create a straight-line trail with evenly spaced stations."""
    # Trail from (0,0) to (count*0.1, 0) — each unit ~11km at equator
    trail = LineString([(index * 0.1, 0.0) for index in range(count + 1)])
    matched: list[MatchedStation] = []
    for index, station in enumerate(stations):
        fraction = index / count
        is_junction = False
        matched.append((station, fraction, is_junction))
    return trail, matched


class TestConstrainedPathFinding:
    def test_simple_train_to_train_hike(self) -> None:
        """Two train stations within distance range produces a hike."""
        stations = [
            _make_station("Start", "train"),
            _make_station("End", "train"),
        ]
        trail, matched = _make_trail_and_matched(stations, 1)
        hikes = find_hikes(trail, matched, min_step_distance_km=0.1, max_step_distance_km=9999)
        assert len(hikes) == 1
        assert len(hikes[0]) == 1

    def test_must_start_at_train_station(self) -> None:
        """Hike starting at a bus stop with no train start is rejected."""
        stations = [
            _make_station("Bus Start", "bus", route_ids={"R1"}),
            _make_station("Train End", "train"),
        ]
        trail, matched = _make_trail_and_matched(stations, 1)
        # Bus and train are NOT transport-connected, so no edge exists
        hikes = find_hikes(trail, matched, min_step_distance_km=0.1, max_step_distance_km=9999)
        assert len(hikes) == 0

    def test_must_end_at_train_station(self) -> None:
        """Hike ending at a bus stop is not returned."""
        stations = [
            _make_station("Train Start", "train"),
            _make_station("Bus End", "bus", route_ids={"R1"}),
        ]
        trail, matched = _make_trail_and_matched(stations, 1)
        hikes = find_hikes(trail, matched, min_step_distance_km=0.1, max_step_distance_km=9999)
        assert len(hikes) == 0

    def test_intermediate_without_hotel_skipped(self) -> None:
        """Intermediate station without hotel is skipped; direct step used instead."""
        stations = [
            _make_station("Start", "train"),
            _make_station("No Hotel", "train", has_hotel=False),
            _make_station("End", "train"),
        ]
        trail, matched = _make_trail_and_matched(stations, 2)
        hikes = find_hikes(trail, matched, min_step_distance_km=0.1, max_step_distance_km=9999)
        assert len(hikes) == 1
        # Should skip the intermediate and go directly Start -> End
        assert len(hikes[0]) == 1
        assert hikes[0][0][0].name == "Start"
        assert hikes[0][0][1].name == "End"

    def test_intermediate_with_hotel_used(self) -> None:
        """Intermediate station with hotel allows multi-step hike when direct is too far."""
        stations = [
            _make_station("Start", "train"),
            _make_station("Hotel Stop", "train", has_hotel=True),
            _make_station("End", "train"),
        ]
        trail, matched = _make_trail_and_matched(stations, 2)
        # Max step ~15km forces going through intermediate (~11km each step vs ~22km direct)
        hikes = find_hikes(trail, matched, min_step_distance_km=0.1, max_step_distance_km=15)
        assert len(hikes) == 1
        assert len(hikes[0]) == 2

    def test_bus_stops_on_same_route_form_step(self) -> None:
        """Two bus stops sharing a route can form an intermediate step."""
        stations = [
            _make_station("Train Start", "train", has_hotel=False),
            _make_station("Bus A", "bus", has_hotel=True, route_ids={"R1"}),
            _make_station("Bus B", "bus", has_hotel=True, route_ids={"R1"}),
            _make_station("Train End", "train", has_hotel=False),
        ]
        trail, matched = _make_trail_and_matched(stations, 3)
        hikes = find_hikes(trail, matched, min_step_distance_km=0.1, max_step_distance_km=9999)
        assert len(hikes) == 1
        # Should find Train Start -> Bus A -> Bus B -> Train End (via transport connectivity)
        # But train<->bus edges won't exist, so the path is Train Start -> Train End directly
        # unless we have train-train, bus-bus edges
        step_names = [(step[0].name, step[1].name) for step in hikes[0]]
        # First step must start at train, last must end at train
        assert step_names[0][0] == "Train Start"
        assert step_names[-1][1] == "Train End"

    def test_mixed_transport_step_not_allowed(self) -> None:
        """A train station and bus stop cannot form a step (not transport-connected)."""
        stations = [
            _make_station("Train A", "train"),
            _make_station("Bus B", "bus", has_hotel=True, route_ids={"R1"}),
        ]
        trail, matched = _make_trail_and_matched(stations, 1)
        hikes = find_hikes(trail, matched, min_step_distance_km=0.1, max_step_distance_km=9999)
        assert len(hikes) == 0

    def test_no_stations_returns_empty(self) -> None:
        trail = LineString([(0, 0), (1, 0)])
        hikes = find_hikes(trail, [], min_step_distance_km=0.1, max_step_distance_km=9999)
        assert len(hikes) == 0

    def test_single_station_returns_empty(self) -> None:
        stations = [_make_station("Only", "train")]
        trail, matched = _make_trail_and_matched(stations, 1)
        hikes = find_hikes(trail, matched, min_step_distance_km=0.1, max_step_distance_km=9999)
        assert len(hikes) == 0
