from __future__ import annotations

import json
from pathlib import Path

from open_rando.commands.pois import build_square_pois, keep_in_square, parse_square
from open_rando.exporters.pois import export_poi_index, export_poi_square, read_poi_index_counts
from open_rando.fetchers.gtfs import FeedData, GtfsStop
from open_rando.fetchers.osm_extract import OsmExtractIndex
from open_rando.fetchers.pois import _parse_accommodation_elements
from open_rando.fetchers.stations import _parse_station_elements
from open_rando.models import PointOfInterest, ServiceWindow, Station
from open_rando.poi_grid import PoiGrid

GRID = PoiGrid()


def _train_station(osm_id: str = "node/1", code: str = "ABC") -> Station:
    return Station(
        name="Gare de Test",
        code=code,
        lat=45.0,
        lon=5.0,
        transport_type="train",
        osm_id=osm_id,
    )


def _bus_stop(osm_id: str = "node/2", code: str = "STOP") -> Station:
    return Station(
        name="Arret Test",
        code=code,
        lat=45.001,
        lon=5.001,
        transport_type="bus",
        osm_id=osm_id,
    )


def _no_feeds(_resource_ids: set[int]) -> FeedData:
    return FeedData()


class TestStableIds:
    def test_station_id_comes_from_osm_type_and_id(self):
        data = {
            "elements": [
                {
                    "type": "way",
                    "id": 42,
                    "lat": 45.0,
                    "lon": 5.0,
                    "tags": {"name": "Gare", "railway": "station"},
                }
            ]
        }
        assert _parse_station_elements(data)[0].osm_id == "way/42"

    def test_accommodation_id_comes_from_osm_type_and_id(self):
        data = {
            "elements": [
                {
                    "type": "node",
                    "id": 7,
                    "lat": 45.0,
                    "lon": 5.0,
                    "tags": {"name": "Hotel", "tourism": "hotel"},
                }
            ]
        }
        assert _parse_accommodation_elements(data)[0].osm_id == "node/7"


class TestBuildSquarePois:
    def test_train_station_keeps_osm_id_and_gets_sncf_url(self):
        pois = build_square_pois([_train_station()], [], {"ABC"}, [], _no_feeds)

        assert [(poi.osm_id, poi.poi_type) for poi in pois] == [("node/1", "train_station")]
        assert pois[0].url is not None and pois[0].url.endswith("/gare-de-test/horaires")

    def test_train_station_outside_sncf_dataset_is_dropped(self):
        pois = build_square_pois([_train_station()], [], {"OTHER"}, [], _no_feeds)

        assert pois == []

    def test_bus_stop_without_gtfs_match_is_kept_with_osm_lines(self):
        stop = _bus_stop()
        stop.transit_lines = ["12"]

        pois = build_square_pois([stop], [], set(), [], _no_feeds)

        assert [(poi.osm_id, poi.transit_lines) for poi in pois] == [("node/2", ["12"])]

    def test_bus_stops_sharing_a_ref_keep_their_own_lines(self):
        first = _bus_stop(osm_id="node/10", code="1")
        second = _bus_stop(osm_id="node/11", code="1")
        second.lat, second.lon = 46.0, 6.0
        near_first = GtfsStop(latitude=45.001, longitude=5.001, stop_id="g1", resource_id=1)
        near_second = GtfsStop(latitude=46.0, longitude=6.0, stop_id="g2", resource_id=1)

        def feeds(_resource_ids: set[int]) -> FeedData:
            return FeedData(
                connectivity={"g1": {"r1"}, "g2": {"r2"}},
                route_names={"r1": "Ligne A", "r2": "Ligne B"},
            )

        pois = build_square_pois([first, second], [], set(), [near_first, near_second], feeds)

        assert {poi.osm_id: poi.transit_lines for poi in pois} == {
            "node/10": ["Ligne A"],
            "node/11": ["Ligne B"],
        }

    def test_bus_stop_with_gtfs_match_gets_line_names(self):
        gtfs_stop = GtfsStop(latitude=45.001, longitude=5.001, stop_id="g1", resource_id=9)

        def feeds(resource_ids: set[int]) -> FeedData:
            assert resource_ids == {9}
            return FeedData(connectivity={"g1": {"r1"}}, route_names={"r1": "Ligne 12"})

        pois = build_square_pois([_bus_stop()], [], set(), [gtfs_stop], feeds)

        assert pois[0].transit_lines == ["Ligne 12"]

    def test_train_station_gets_rail_service_from_matched_gtfs_stop(self):
        gtfs_stop = GtfsStop(latitude=45.0, longitude=5.0, stop_id="g2", resource_id=3)
        window = ServiceWindow(
            first_departure_minutes=360, last_departure_minutes=1200, departure_count=20
        )

        def feeds(_resource_ids: set[int]) -> FeedData:
            return FeedData(departures={"g2": {"weekday": window}})

        pois = build_square_pois([_train_station()], [], {"ABC"}, [gtfs_stop], feeds)

        assert pois[0].rail_service is not None
        assert pois[0].rail_service.weekday == window

    def test_accommodation_is_passed_through(self):
        hotel = PointOfInterest(name="Hotel", lat=45.0, lon=5.0, poi_type="hotel", osm_id="node/9")

        pois = build_square_pois([], [hotel], set(), [], _no_feeds)

        assert [poi.osm_id for poi in pois] == ["node/9"]


class TestSquareOwnership:
    def test_poi_on_shared_edge_belongs_to_one_square_only(self):
        boundary_lon = GRID.square_bounding_box((7, 3))[2]
        poi = PointOfInterest(
            name="Edge", lat=45.5, lon=boundary_lon, poi_type="hotel", osm_id="node/5"
        )

        assert keep_in_square([poi], GRID, (7, 3)) == []
        assert keep_in_square([poi], GRID, (8, 3)) == [poi]


class TestExport:
    def test_square_file_is_sorted_by_id_and_free_of_trail_fields(self, tmp_path: Path):
        pois = [
            PointOfInterest(name="B", lat=45.0, lon=5.0, poi_type="hotel", osm_id="node/20"),
            PointOfInterest(name="A", lat=45.0, lon=5.0, poi_type="camping", osm_id="node/10"),
        ]

        export_poi_square((8, 3), pois, str(tmp_path))

        written = json.loads((tmp_path / "8_3.json").read_text(encoding="utf-8"))
        assert [entry["id"] for entry in written["pois"]] == ["node/10", "node/20"]
        assert "distance_km" not in written["pois"][0]

    def test_index_lists_empty_built_squares_too(self, tmp_path: Path):
        export_poi_index(GRID, {(8, 3): 2, (0, 0): 0}, str(tmp_path))

        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert index["squares"] == [
            {"col": 0, "row": 0, "count": 0},
            {"col": 8, "row": 3, "count": 2},
        ]
        assert index["grid"]["cols"] == 12

    def test_partial_rerun_keeps_counts_of_other_squares(self, tmp_path: Path):
        export_poi_index(GRID, {(8, 3): 2}, str(tmp_path))

        assert read_poi_index_counts(str(tmp_path)) == {(8, 3): 2}


def test_parse_square():
    assert parse_square("8_3") == (8, 3)


class TestExtractCoverageClipping:
    """The grid starts at 41.0 N; the France extract covers 41.24 N to 51.43 N."""

    def _index(self, tmp_path: Path, bbox: dict[str, float] | None) -> OsmExtractIndex:
        index = OsmExtractIndex.open_for_writing(tmp_path / "index.sqlite")
        index.connection.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            ("layer:stations", json.dumps({"bbox": bbox})),
        )
        index.connection.commit()
        return index

    def test_square_reaching_past_the_extract_is_clipped_to_it(self, tmp_path: Path):
        index = self._index(
            tmp_path, {"south": 41.24, "west": -6.94, "north": 51.43, "east": 10.02}
        )

        clipped = index.clip_to_coverage("stations", 41.0, -5.5, 42.3, -4.2)

        assert clipped == (41.24, -5.5, 42.3, -4.2)

    def test_square_inside_the_extract_is_unchanged(self, tmp_path: Path):
        index = self._index(
            tmp_path, {"south": 41.24, "west": -6.94, "north": 51.43, "east": 10.02}
        )

        assert index.clip_to_coverage("stations", 45.0, 5.0, 46.0, 6.0) == (45.0, 5.0, 46.0, 6.0)

    def test_square_entirely_outside_the_extract_has_no_part(self, tmp_path: Path):
        index = self._index(
            tmp_path, {"south": 41.24, "west": -6.94, "north": 51.43, "east": 10.02}
        )

        assert index.clip_to_coverage("stations", 30.0, 0.0, 31.0, 1.0) is None

    def test_extract_without_recorded_bbox_is_trusted_as_is(self, tmp_path: Path):
        index = self._index(tmp_path, None)

        assert index.clip_to_coverage("stations", 41.0, -5.5, 42.3, -4.2) == (
            41.0,
            -5.5,
            42.3,
            -4.2,
        )

    def test_unknown_layer_has_no_part(self, tmp_path: Path):
        index = self._index(tmp_path, None)

        assert index.clip_to_coverage("accommodation", 41.0, -5.5, 42.3, -4.2) is None
