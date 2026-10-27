from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import LineString

from open_rando.exporters.links import export_links, load_link_counts, load_links
from open_rando.exporters.pois import export_poi_index, export_poi_square
from open_rando.models import PoiLink, PointOfInterest, RailService, ServiceWindow
from open_rando.poi_grid import PoiGrid
from open_rando.poi_store import PoiGridMissingError, read_poi_squares
from open_rando.processors.link import link_pois_to_trail, summarize_links

GRID = PoiGrid()

# About 15.7 km east-west at latitude 45. 0.01 degree of latitude is ~1.1 km.
TRAIL = LineString([(5.0, 45.0), (5.2, 45.0)])


def _poi(kind: str, osm_id: str, lat: float, lon: float) -> PointOfInterest:
    return PointOfInterest(name=osm_id, lat=lat, lon=lon, poi_type=kind, osm_id=osm_id)


def _link(pois: list[PointOfInterest]) -> dict[str, PoiLink]:
    links = link_pois_to_trail(TRAIL, pois, refine_junctions=False)
    return {link.poi_id: link for link in links}


class TestLinkPoisToTrail:
    def test_train_station_gets_position_along_trail(self):
        links = _link([_poi("train_station", "node/1", 45.002, 5.1)])

        assert links["node/1"].distance_km == pytest.approx(7.85, abs=0.1)

    def test_train_station_gets_distance_to_trail(self):
        links = _link([_poi("train_station", "node/1", 45.002, 5.1)])

        assert links["node/1"].distance_to_trail_meters == pytest.approx(220, rel=0.2)

    def test_train_station_gets_junction_on_trail(self):
        links = _link([_poi("train_station", "node/1", 45.002, 5.1)])

        assert links["node/1"].junction == pytest.approx((5.1, 45.0), abs=1e-3)

    def test_train_station_beyond_five_kilometres_is_not_linked(self):
        # Inside the candidate zone (6.7 km) but past the 5 km station limit.
        assert _link([_poi("train_station", "node/1", 45.06, 5.1)]) == {}

    def test_bus_stop_within_two_kilometres_is_linked_without_position(self):
        links = _link([_poi("bus_stop", "node/2", 45.01, 5.1)])

        assert links["node/2"].distance_km is None

    def test_bus_stop_beyond_two_kilometres_is_not_linked(self):
        assert _link([_poi("bus_stop", "node/2", 45.03, 5.1)]) == {}

    def test_hotel_within_three_kilometres_is_linked(self):
        assert "node/3" in _link([_poi("hotel", "node/3", 45.02, 5.1)])

    def test_camping_beyond_three_kilometres_is_not_linked(self):
        assert _link([_poi("camping", "node/4", 45.04, 5.1)]) == {}

    def test_poi_far_from_trail_is_ignored(self):
        assert _link([_poi("hotel", "node/5", 48.0, 2.0)]) == {}

    def test_train_stations_come_first_in_trail_order_then_others(self):
        pois = [
            _poi("hotel", "node/10", 45.001, 5.05),
            _poi("train_station", "node/11", 45.001, 5.15),
            _poi("train_station", "node/12", 45.001, 5.05),
            _poi("bus_stop", "node/13", 45.001, 5.1),
        ]

        links = link_pois_to_trail(TRAIL, pois, refine_junctions=False)

        assert [link.poi_id for link in links[:2]] == ["node/12", "node/11"]
        assert {link.poi_id for link in links[2:]} == {"node/10", "node/13"}

    def test_link_keeps_the_poi_identity(self):
        links = _link([_poi("hotel", "way/77", 45.001, 5.1)])

        assert links["way/77"].kind == "hotel"


class TestSummarizeLinks:
    def test_counts_each_kind_and_stations_with_departures(self):
        served = _poi("train_station", "node/1", 45.0, 5.1)
        served.rail_service = RailService(
            weekday=ServiceWindow(
                first_departure_minutes=360, last_departure_minutes=1200, departure_count=10
            )
        )
        unserved = _poi("train_station", "node/2", 45.0, 5.15)
        hotel = _poi("hotel", "node/3", 45.001, 5.1)
        pois = [served, unserved, hotel]
        # Station filtering looks at trail vertices, so the trail needs some near each station.
        dense_trail = LineString([(5.0 + step * 0.005, 45.0) for step in range(41)])

        counts = summarize_links(
            link_pois_to_trail(dense_trail, pois, refine_junctions=False), pois
        )

        assert counts == {
            "train_station": 2,
            "bus_stop": 0,
            "hotel": 1,
            "camping": 0,
            "train_station_with_rail_service": 1,
        }


class TestLinkFiles:
    def test_links_round_trip(self, tmp_path: Path):
        links = [
            PoiLink("node/1", "train_station", 220.0, distance_km=7.85, junction=(5.1, 45.0)),
            PoiLink("node/2", "hotel", 900.5),
        ]

        counts = {
            "train_station": 1,
            "bus_stop": 0,
            "hotel": 1,
            "camping": 0,
            "train_station_with_rail_service": 0,
        }

        export_links("route1", links, counts, tmp_path)

        assert load_links("route1", tmp_path) == links
        assert load_link_counts("route1", tmp_path) == counts


class TestReadPoiSquares:
    def _build(self, directory: Path, counts: dict[tuple[int, int], int]) -> None:
        poi = _poi("hotel", "node/9", 45.0, 5.0)
        for square, count in counts.items():
            if count:
                export_poi_square(square, [poi], str(directory))
        export_poi_index(GRID, counts, str(directory))

    def test_reads_pois_of_built_squares(self, tmp_path: Path):
        self._build(tmp_path, {(8, 3): 1})

        pois = read_poi_squares(tmp_path, GRID, [(8, 3)])

        assert [poi.osm_id for poi in pois] == ["node/9"]

    def test_built_but_empty_square_reads_as_empty(self, tmp_path: Path):
        self._build(tmp_path, {(8, 3): 1, (0, 0): 0})

        assert read_poi_squares(tmp_path, GRID, [(0, 0)]) == []

    def test_unbuilt_square_is_an_error_not_an_empty_result(self, tmp_path: Path):
        self._build(tmp_path, {(8, 3): 1})

        with pytest.raises(PoiGridMissingError, match="not built: 9_3"):
            read_poi_squares(tmp_path, GRID, [(8, 3), (9, 3)])

    def test_missing_index_is_an_error(self, tmp_path: Path):
        with pytest.raises(PoiGridMissingError, match="Run `python -m open_rando pois`"):
            read_poi_squares(tmp_path, GRID, [(8, 3)])

    def test_index_built_on_another_grid_is_an_error(self, tmp_path: Path):
        self._build(tmp_path, {(8, 3): 1})
        index_path = tmp_path / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["grid"]["cols"] = 24
        index_path.write_text(json.dumps(index), encoding="utf-8")

        with pytest.raises(PoiGridMissingError, match="different grid"):
            read_poi_squares(tmp_path, GRID, [(8, 3)])
