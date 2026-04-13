from __future__ import annotations

from open_rando.fetchers.gtfs import (
    GtfsStop,
    are_stations_transport_connected,
    filter_and_annotate_bus_stops,
    resolve_transit_line_names,
)
from open_rando.fetchers.stations import (
    _detect_transport_type,
    _extract_code,
    _parse_station_elements,
    filter_stations_by_sncf,
)
from open_rando.models import Station


def _make_station(
    name: str, code: str, transport_type: str = "train", lat: float = 48.0, lon: float = 2.0
) -> Station:
    return Station(name=name, code=code, lat=lat, lon=lon, transport_type=transport_type)


class TestDetectTransportType:
    def test_railway_station(self) -> None:
        assert _detect_transport_type({"railway": "station"}) == "train"

    def test_railway_halt(self) -> None:
        assert _detect_transport_type({"railway": "halt"}) == "train"

    def test_highway_bus_stop(self) -> None:
        assert _detect_transport_type({"highway": "bus_stop"}) == "bus"

    def test_public_transport_platform_bus(self) -> None:
        assert _detect_transport_type({"public_transport": "platform", "bus": "yes"}) == "bus"

    def test_public_transport_platform_without_bus(self) -> None:
        assert _detect_transport_type({"public_transport": "platform"}) == "train"

    def test_unknown_defaults_to_train(self) -> None:
        assert _detect_transport_type({}) == "train"


class TestExtractCode:
    def test_train_sncf_ref(self) -> None:
        assert _extract_code({"ref:SNCF": "PSL"}, 12345, "train") == "PSL"

    def test_train_railway_ref(self) -> None:
        assert _extract_code({"railway:ref": "AB"}, 12345, "train") == "AB"

    def test_train_fallback_osm_id(self) -> None:
        assert _extract_code({}, 12345, "train") == "12345"

    def test_bus_ref(self) -> None:
        assert _extract_code({"ref": "BUS123"}, 99999, "bus") == "BUS123"

    def test_bus_stif_ref(self) -> None:
        assert _extract_code({"ref:FR:STIF": "STIF456"}, 99999, "bus") == "STIF456"

    def test_bus_idfm_ref(self) -> None:
        assert _extract_code({"ref:FR:IDFM": "IDFM789"}, 99999, "bus") == "IDFM789"

    def test_bus_fallback_osm_id(self) -> None:
        assert _extract_code({}, 99999, "bus") == "99999"


class TestParseStationElements:
    def test_parses_train_station(self) -> None:
        data = {
            "elements": [
                {
                    "id": 1,
                    "tags": {"name": "Gare de Test", "railway": "station", "ref:SNCF": "TST"},
                    "lat": 48.0,
                    "lon": 2.0,
                }
            ]
        }
        stations = _parse_station_elements(data)
        assert len(stations) == 1
        assert stations[0].transport_type == "train"
        assert stations[0].code == "TST"

    def test_parses_bus_stop(self) -> None:
        data = {
            "elements": [
                {
                    "id": 2,
                    "tags": {"name": "Arrêt Centre", "highway": "bus_stop", "ref": "BUS1"},
                    "lat": 48.1,
                    "lon": 2.1,
                }
            ]
        }
        stations = _parse_station_elements(data)
        assert len(stations) == 1
        assert stations[0].transport_type == "bus"
        assert stations[0].code == "BUS1"

    def test_skips_unnamed_bus_stop(self) -> None:
        data = {
            "elements": [
                {
                    "id": 3,
                    "tags": {"highway": "bus_stop"},
                    "lat": 48.0,
                    "lon": 2.0,
                }
            ]
        }
        assert _parse_station_elements(data) == []

    def test_mixed_train_and_bus(self) -> None:
        data = {
            "elements": [
                {
                    "id": 1,
                    "tags": {"name": "Gare", "railway": "station", "ref:SNCF": "GAR"},
                    "lat": 48.0,
                    "lon": 2.0,
                },
                {
                    "id": 2,
                    "tags": {"name": "Bus Stop", "highway": "bus_stop"},
                    "lat": 48.1,
                    "lon": 2.1,
                },
            ]
        }
        stations = _parse_station_elements(data)
        assert len(stations) == 2
        types = {station.transport_type for station in stations}
        assert types == {"train", "bus"}

    def test_bus_stop_uses_route_ref_for_transit_lines(self) -> None:
        data = {
            "elements": [
                {
                    "id": 1,
                    "tags": {"name": "Stop A", "highway": "bus_stop", "route_ref": "12;34"},
                    "lat": 48.0,
                    "lon": 2.0,
                }
            ]
        }
        stations = _parse_station_elements(data)
        assert stations[0].transit_lines == ["12", "34"]


class TestFilterStationsBySncfWithBusStops:
    def test_bus_stops_pass_through(self) -> None:
        stations = [
            _make_station("Bus Stop", "BUS1", "bus"),
            _make_station("Train Station", "PSL", "train"),
        ]
        filtered = filter_stations_by_sncf(stations, {"PSL"})
        assert len(filtered) == 2

    def test_unverified_train_dropped_but_bus_kept(self) -> None:
        stations = [
            _make_station("Bus Stop", "BUS1", "bus"),
            _make_station("Unknown Train", "UNKNOWN", "train"),
        ]
        filtered = filter_stations_by_sncf(stations, {"PSL"})
        assert len(filtered) == 1
        assert filtered[0].transport_type == "bus"


class TestFilterAndAnnotateBusStops:
    def test_train_stations_always_pass(self) -> None:
        stations = [_make_station("Train", "T1", "train")]
        filtered, gtfs_map = filter_and_annotate_bus_stops(stations, [])
        assert len(filtered) == 1
        assert filtered[0].transport_type == "train"

    def test_bus_stop_near_gtfs_kept(self) -> None:
        stations = [_make_station("Bus", "B1", "bus", lat=48.0, lon=2.0)]
        gtfs_stops = [GtfsStop(latitude=48.0004, longitude=2.0004, stop_id="S1", resource_id=1)]
        filtered, gtfs_map = filter_and_annotate_bus_stops(stations, gtfs_stops)
        assert len(filtered) == 1
        assert "B1" in gtfs_map

    def test_bus_stop_far_from_gtfs_dropped(self) -> None:
        stations = [_make_station("Bus", "B1", "bus", lat=48.0, lon=2.0)]
        gtfs_stops = [GtfsStop(latitude=48.05, longitude=2.05, stop_id="S1", resource_id=1)]
        filtered, gtfs_map = filter_and_annotate_bus_stops(stations, gtfs_stops)
        assert len(filtered) == 0

    def test_no_gtfs_data_drops_all_bus_stops(self) -> None:
        stations = [
            _make_station("Bus", "B1", "bus"),
            _make_station("Train", "T1", "train"),
        ]
        filtered, gtfs_map = filter_and_annotate_bus_stops(stations, [])
        assert len(filtered) == 1
        assert filtered[0].transport_type == "train"

    def test_mixed_stations_filtering(self) -> None:
        stations = [
            _make_station("Train", "T1", "train", lat=48.0, lon=2.0),
            _make_station("Bus Near", "B1", "bus", lat=48.0, lon=2.001),
            _make_station("Bus Far", "B2", "bus", lat=49.0, lon=3.0),
        ]
        gtfs_stops = [GtfsStop(latitude=48.0, longitude=2.001, stop_id="S1", resource_id=1)]
        filtered, gtfs_map = filter_and_annotate_bus_stops(stations, gtfs_stops)
        assert len(filtered) == 2
        names = {station.name for station in filtered}
        assert names == {"Train", "Bus Near"}


class TestAreStationsTransportConnected:
    def test_both_train_stations_connected(self) -> None:
        station_a = _make_station("Train A", "TA", "train")
        station_b = _make_station("Train B", "TB", "train")
        station_a.connected_route_ids = {"__train__"}
        station_b.connected_route_ids = {"__train__"}
        assert are_stations_transport_connected(station_a, station_b) is True

    def test_both_bus_same_route_connected(self) -> None:
        station_a = _make_station("Bus A", "BA", "bus")
        station_b = _make_station("Bus B", "BB", "bus")
        station_a.connected_route_ids = {"R1", "R2"}
        station_b.connected_route_ids = {"R2", "R3"}
        assert are_stations_transport_connected(station_a, station_b) is True

    def test_bus_stops_no_shared_route_not_connected(self) -> None:
        station_a = _make_station("Bus A", "BA", "bus")
        station_b = _make_station("Bus B", "BB", "bus")
        station_a.connected_route_ids = {"R1"}
        station_b.connected_route_ids = {"R2"}
        assert are_stations_transport_connected(station_a, station_b) is False

    def test_train_and_bus_not_connected(self) -> None:
        station_a = _make_station("Train", "TA", "train")
        station_b = _make_station("Bus", "BB", "bus")
        station_a.connected_route_ids = {"__train__"}
        station_b.connected_route_ids = {"R1"}
        assert are_stations_transport_connected(station_a, station_b) is False

    def test_empty_routes_not_connected(self) -> None:
        station_a = _make_station("A", "A1", "bus")
        station_b = _make_station("B", "B1", "bus")
        assert are_stations_transport_connected(station_a, station_b) is False


class TestResolveTransitLineNames:
    def test_resolves_known_routes(self) -> None:
        route_names = {"R1": "42 — Paris - Versailles", "R2": "57 — Mantes - Poissy"}
        result = resolve_transit_line_names({"R1", "R2"}, route_names)
        assert result == ["42 — Paris - Versailles", "57 — Mantes - Poissy"]

    def test_falls_back_to_route_id(self) -> None:
        result = resolve_transit_line_names({"R1"}, {})
        assert result == ["R1"]

    def test_skips_train_sentinel(self) -> None:
        result = resolve_transit_line_names({"__train__", "R1"}, {"R1": "Line 1"})
        assert result == ["Line 1"]

    def test_empty_route_ids(self) -> None:
        result = resolve_transit_line_names(set(), {"R1": "Line 1"})
        assert result == []

    def test_sorted_alphabetically(self) -> None:
        route_names = {"R1": "Z Line", "R2": "A Line"}
        result = resolve_transit_line_names({"R1", "R2"}, route_names)
        assert result == ["A Line", "Z Line"]
