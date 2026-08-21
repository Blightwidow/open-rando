from __future__ import annotations

from pathlib import Path

import pytest

from open_rando.fetchers import osm_extract
from open_rando.fetchers.osm_extract import (
    LAYER_ACCOMMODATION,
    LAYER_FOREST,
    LAYER_STATIONS,
    LAYER_TRAILS,
    OsmExtractIndex,
    is_accommodation_tagged,
    is_forest_tagged,
    is_station_tagged,
    is_trail_relation_tagged,
    landmark_kind_for_tags,
    open_layer,
)


class TestTagMatching:
    @pytest.mark.parametrize(
        "tags",
        [
            {"railway": "station"},
            {"railway": "halt"},
            {"highway": "bus_stop"},
            {"public_transport": "platform", "bus": "yes"},
        ],
    )
    def test_matches_the_overpass_station_selectors(self, tags: dict[str, str]) -> None:
        assert is_station_tagged(tags) is True

    @pytest.mark.parametrize(
        "tags",
        [
            {"railway": "station", "disused": "yes"},
            {"railway": "halt", "abandoned": "yes"},
            {"public_transport": "platform"},
            {"railway": "rail"},
            {},
        ],
    )
    def test_rejects_what_overpass_filters_out(self, tags: dict[str, str]) -> None:
        assert is_station_tagged(tags) is False

    def test_matches_accommodation_kinds(self) -> None:
        assert is_accommodation_tagged({"tourism": "camp_site"}) is True
        assert is_accommodation_tagged({"tourism": "museum"}) is False

    def test_returns_the_landmark_kind(self) -> None:
        assert landmark_kind_for_tags({"historic": "castle"}) == "castle"
        assert landmark_kind_for_tags({"natural": "peak"}) == "peak"
        assert landmark_kind_for_tags({"natural": "tree"}) is None

    def test_matches_forest_tags(self) -> None:
        assert is_forest_tagged({"landuse": "forest"}) is True
        assert is_forest_tagged({"natural": "wood"}) is True
        assert is_forest_tagged({"landuse": "meadow"}) is False

    def test_matches_hiking_relations(self) -> None:
        assert is_trail_relation_tagged({"route": "hiking"}) is True
        assert is_trail_relation_tagged({"route": "bicycle"}) is False


@pytest.fixture
def index(tmp_path: Path) -> OsmExtractIndex:
    return OsmExtractIndex.open_for_writing(tmp_path / "index.sqlite")


class TestPointQueries:
    def test_returns_points_inside_the_bounding_box(self, index: OsmExtractIndex) -> None:
        index.insert_points(
            LAYER_STATIONS,
            [
                ("node", 1, 48.5, 2.5, {"railway": "station", "name": "Inside"}),
                ("node", 2, 40.0, 2.5, {"railway": "station", "name": "Too far south"}),
                ("node", 3, 48.5, 9.0, {"railway": "station", "name": "Too far east"}),
            ],
        )
        index.commit()

        elements = index.point_elements(LAYER_STATIONS, 48.0, 2.0, 49.0, 3.0)["elements"]

        assert [element["tags"]["name"] for element in elements] == ["Inside"]

    def test_shapes_elements_like_an_overpass_response(self, index: OsmExtractIndex) -> None:
        index.insert_points(
            LAYER_ACCOMMODATION, [("way", 7, 48.5, 2.5, {"tourism": "hotel", "name": "Hotel"})]
        )
        index.commit()

        [element] = index.point_elements(LAYER_ACCOMMODATION, 48.0, 2.0, 49.0, 3.0)["elements"]

        assert element == {
            "type": "way",
            "id": 7,
            "lat": 48.5,
            "lon": 2.5,
            "tags": {"tourism": "hotel", "name": "Hotel"},
        }

    def test_keeps_layers_apart(self, index: OsmExtractIndex) -> None:
        index.insert_points(LAYER_STATIONS, [("node", 1, 48.5, 2.5, {"railway": "station"})])
        index.commit()

        assert index.point_elements(LAYER_ACCOMMODATION, 48.0, 2.0, 49.0, 3.0)["elements"] == []


class TestAreaQueries:
    def test_returns_areas_overlapping_the_bounding_box(self, index: OsmExtractIndex) -> None:
        index.insert_areas(
            LAYER_FOREST,
            [
                ("way", 1, [(48.4, 2.4), (48.6, 2.4), (48.6, 2.6), (48.4, 2.4)]),
                ("way", 2, [(41.0, 2.4), (41.2, 2.4), (41.2, 2.6), (41.0, 2.4)]),
            ],
        )
        index.commit()

        elements = index.area_elements(LAYER_FOREST, 48.45, 2.45, 48.5, 2.5)["elements"]

        assert [element["id"] for element in elements] == [1]
        assert elements[0]["geometry"][0] == {"lat": 48.4, "lon": 2.4}

    def test_drops_rings_with_too_few_points(self, index: OsmExtractIndex) -> None:
        inserted = index.insert_areas(LAYER_FOREST, [("way", 3, [(48.4, 2.4), (48.5, 2.5)])])

        assert inserted == 0


class TestTrailQueries:
    def test_assembles_a_superroute_with_children_and_ways(self, index: OsmExtractIndex) -> None:
        index.insert_trail_relations(
            [
                (
                    100,
                    {"route": "hiking", "ref": "GR 1", "name": "Tour"},
                    [{"type": "relation", "ref": 101, "role": ""}],
                ),
                (
                    101,
                    {"route": "hiking", "ref": "GR 1"},
                    [{"type": "way", "ref": 10, "role": ""}],
                ),
            ]
        )
        index.insert_trail_ways([(10, [(48.5, 2.5), (48.6, 2.6)])])
        index.commit()

        data = index.trail_elements(100)

        assert data is not None
        types = [(element["type"], element["id"]) for element in data["elements"]]
        assert types == [("relation", 100), ("relation", 101), ("way", 10)]
        way = data["elements"][2]
        assert way["geometry"] == [{"lat": 48.5, "lon": 2.5}, {"lat": 48.6, "lon": 2.6}]

    def test_returns_ways_of_a_simple_route(self, index: OsmExtractIndex) -> None:
        index.insert_trail_relations(
            [(200, {"route": "hiking"}, [{"type": "way", "ref": 20, "role": ""}])]
        )
        index.insert_trail_ways([(20, [(48.5, 2.5), (48.6, 2.6)])])
        index.commit()

        data = index.trail_elements(200)

        assert data is not None
        assert [element["type"] for element in data["elements"]] == ["relation", "way"]

    def test_returns_none_for_an_unknown_relation(self, index: OsmExtractIndex) -> None:
        assert index.trail_elements(999) is None

    def test_returns_none_when_a_member_way_is_clipped_away(self, index: OsmExtractIndex) -> None:
        """A route reaching outside the extract must fall back to Overpass."""
        index.insert_trail_relations(
            [
                (
                    300,
                    {"route": "hiking"},
                    [
                        {"type": "way", "ref": 30, "role": ""},
                        {"type": "way", "ref": 31, "role": ""},
                    ],
                )
            ]
        )
        index.insert_trail_ways([(30, [(48.5, 2.5), (48.6, 2.6)])])
        index.commit()

        assert index.trail_elements(300) is None


class TestLayerAvailability:
    def test_open_layer_returns_none_without_an_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(osm_extract, "default_index_path", lambda: tmp_path / "missing.sqlite")

        assert open_layer(LAYER_STATIONS) is None

    def test_open_layer_returns_none_for_an_unbuilt_layer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        index_path = tmp_path / "index.sqlite"
        index = OsmExtractIndex.open_for_writing(index_path)
        index.insert_points(LAYER_STATIONS, [("node", 1, 48.5, 2.5, {"railway": "station"})])
        index.record_layer(LAYER_STATIONS, 1, "stations.osm.pbf")
        index.close()
        monkeypatch.setattr(osm_extract, "default_index_path", lambda: index_path)

        assert open_layer(LAYER_STATIONS) is not None
        assert open_layer(LAYER_TRAILS) is None

    def test_open_layer_refuses_a_bbox_outside_the_extract(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        index_path = tmp_path / "index.sqlite"
        index = OsmExtractIndex.open_for_writing(index_path)
        index.insert_points(LAYER_STATIONS, [("node", 1, 46.5, 4.5, {"railway": "station"})])
        # A Bourgogne-sized extract.
        index.record_layer(LAYER_STATIONS, 1, "stations.osm.pbf", (46.0, 2.8, 48.4, 5.5))
        index.close()
        monkeypatch.setattr(osm_extract, "default_index_path", lambda: index_path)

        inside = open_layer(LAYER_STATIONS, (46.4, 4.4, 46.6, 4.6))
        assert inside is not None
        inside.close()

        # Brittany: inside France, outside this extract.
        assert open_layer(LAYER_STATIONS, (48.0, -3.0, 48.3, -2.5)) is None

    def test_open_layer_trusts_a_layer_without_recorded_coverage(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        index_path = tmp_path / "index.sqlite"
        index = OsmExtractIndex.open_for_writing(index_path)
        index.insert_points(LAYER_STATIONS, [("node", 1, 46.5, 4.5, {"railway": "station"})])
        index.record_layer(LAYER_STATIONS, 1, "stations.osm.pbf")
        index.close()
        monkeypatch.setattr(osm_extract, "default_index_path", lambda: index_path)

        index_for_query = open_layer(LAYER_STATIONS, (48.0, -3.0, 48.3, -2.5))
        assert index_for_query is not None
        index_for_query.close()

    def test_a_layer_recorded_as_empty_counts_as_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        index_path = tmp_path / "index.sqlite"
        index = OsmExtractIndex.open_for_writing(index_path)
        index.record_layer(LAYER_FOREST, 0, "forest.osm.pbf")
        index.close()
        monkeypatch.setattr(osm_extract, "default_index_path", lambda: index_path)

        assert open_layer(LAYER_FOREST) is None
