from __future__ import annotations

from open_rando.fetchers.sncf import build_sncf_code_set
from open_rando.fetchers.stations import filter_stations_by_sncf
from open_rando.models import Station


def _make_station(name: str, code: str) -> Station:
    return Station(name=name, code=code, lat=48.0, lon=2.0)


class TestBuildSncfCodeSet:
    def test_includes_trigramme_and_uic(self) -> None:
        records = [{"libellecourt": "PSL", "codes_uic": "8727100"}]
        codes = build_sncf_code_set(records)
        assert "PSL" in codes
        assert "8727100" in codes

    def test_eight_digit_uic_produces_seven_digit_variant(self) -> None:
        records = [{"libellecourt": "CME", "codes_uic": "87682450"}]
        codes = build_sncf_code_set(records)
        assert "87682450" in codes  # raw 8-digit
        assert "8768245" in codes  # 7-digit (drop check digit)
        assert "682450" in codes  # without 87 prefix

    def test_short_uic_gets_87_prefix_added(self) -> None:
        records = [{"libellecourt": "XYZ", "codes_uic": "12345"}]
        codes = build_sncf_code_set(records)
        assert "12345" in codes
        assert "8712345" in codes

    def test_empty_records(self) -> None:
        assert build_sncf_code_set([]) == set()

    def test_missing_fields_skipped(self) -> None:
        records = [{"libellecourt": "", "codes_uic": None}, {"nom": "Test"}]
        codes = build_sncf_code_set(records)
        assert codes == set()


class TestFilterStationsBySncf:
    def test_keeps_matching_stations(self) -> None:
        stations = [_make_station("Paris Saint-Lazare", "PSL")]
        filtered = filter_stations_by_sncf(stations, {"PSL", "8727100"})
        assert len(filtered) == 1
        assert filtered[0].name == "Paris Saint-Lazare"

    def test_drops_unmatched_stations(self) -> None:
        stations = [_make_station("Unknown Halt", "9999999999")]
        filtered = filter_stations_by_sncf(stations, {"PSL"})
        assert len(filtered) == 0

    def test_mixed_keeps_and_drops(self) -> None:
        stations = [
            _make_station("Paris Saint-Lazare", "PSL"),
            _make_station("Private Railway", "12345678901"),
            _make_station("Fontainebleau-Avon", "8768831"),
        ]
        sncf_codes = {"PSL", "8768831", "68831"}
        filtered = filter_stations_by_sncf(stations, sncf_codes)
        assert len(filtered) == 2
        assert {station.name for station in filtered} == {
            "Paris Saint-Lazare",
            "Fontainebleau-Avon",
        }

    def test_empty_sncf_codes_drops_all(self) -> None:
        stations = [_make_station("Test", "ABC")]
        filtered = filter_stations_by_sncf(stations, set())
        assert len(filtered) == 0

    def test_empty_stations_returns_empty(self) -> None:
        filtered = filter_stations_by_sncf([], {"PSL"})
        assert filtered == []
