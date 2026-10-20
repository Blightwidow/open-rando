"""Build the extract index from synthetic PBFs and query it through the fetchers.

The .osm.pbf inputs are written with pyosmium instead of osmium-tool, so the
whole indexing path is exercised without the 5GB France extract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString

from open_rando.commands.osm_index import EXTRACT_FILENAMES, build_layer, extract_bbox
from open_rando.fetchers import landmarks as landmarks_module
from open_rando.fetchers import osm_extract
from open_rando.fetchers import pois as pois_module
from open_rando.fetchers import stations as stations_module
from open_rando.fetchers.osm_extract import (
    LAYER_ACCOMMODATION,
    LAYER_FOREST,
    LAYER_LANDMARKS,
    LAYER_STATIONS,
    LAYER_TRAILS,
    OsmExtractIndex,
)
from open_rando.fetchers.overpass import fetch_trail
from open_rando.processors import geography as geography_module

osmium = pytest.importorskip("osmium")


def write_pbf(path: Path, nodes: list[dict], ways: list[dict], relations: list[dict]) -> Path:
    """Write a small .osm.pbf. Node locations are (lon, lat), as osmium wants."""
    from osmium.osm import mutable

    writer = osmium.SimpleWriter(str(path))
    try:
        for node in nodes:
            writer.add_node(mutable.Node(**node))
        for way in ways:
            writer.add_way(mutable.Way(**way))
        for relation in relations:
            writer.add_relation(mutable.Relation(**relation))
    finally:
        writer.close()
    return path


@pytest.fixture
def extracts_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "extracts"
    directory.mkdir()

    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_STATIONS],
        nodes=[
            {"id": 1, "location": (2.50, 48.50), "tags": {"railway": "station", "name": "Melun"}},
            {"id": 2, "location": (2.60, 48.60), "tags": {"railway": "halt", "name": "Broye"}},
            {"id": 3, "location": (2.55, 48.55), "tags": {"highway": "bus_stop", "name": "Mairie"}},
            {
                "id": 4,
                "location": (2.52, 48.52),
                "tags": {"railway": "station", "disused": "yes", "name": "Closed"},
            },
            {"id": 5, "location": (9.00, 48.50), "tags": {"railway": "station", "name": "Far"}},
        ],
        ways=[],
        relations=[],
    )

    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_ACCOMMODATION],
        nodes=[
            {"id": 11, "location": (2.51, 48.51), "tags": {"tourism": "hotel", "name": "Hotel"}},
            {"id": 12, "location": (2.40, 48.40), "tags": {}},
            {"id": 13, "location": (2.44, 48.44), "tags": {}},
        ],
        ways=[
            {
                "id": 20,
                "nodes": [12, 13],
                "tags": {"tourism": "camp_site", "name": "Camping du Lac"},
            }
        ],
        relations=[],
    )

    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_LANDMARKS],
        nodes=[
            {
                "id": 31,
                "location": (2.53, 48.53),
                "tags": {"historic": "castle", "name": "Chateau", "ele": "180"},
            },
            {"id": 32, "location": (2.54, 48.54), "tags": {"natural": "tree", "name": "Arbre"}},
        ],
        ways=[],
        relations=[],
    )

    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_FOREST],
        nodes=[
            {"id": 41, "location": (2.40, 48.40), "tags": {}},
            {"id": 42, "location": (2.70, 48.40), "tags": {}},
            {"id": 43, "location": (2.70, 48.70), "tags": {}},
            {"id": 51, "location": (5.10, 45.10), "tags": {}},
            {"id": 52, "location": (5.20, 45.10), "tags": {}},
            {"id": 53, "location": (5.20, 45.20), "tags": {}},
        ],
        ways=[
            {"id": 60, "nodes": [41, 42, 43, 41], "tags": {"landuse": "forest", "name": "Bois"}},
            {"id": 61, "nodes": [51, 52, 53, 51], "tags": {}},
        ],
        relations=[
            {
                "id": 70,
                "members": [("w", 61, "outer")],
                "tags": {"type": "multipolygon", "natural": "wood", "name": "Grande foret"},
            }
        ],
    )

    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_TRAILS],
        nodes=[
            {"id": 81, "location": (2.50, 48.50), "tags": {}},
            {"id": 82, "location": (2.55, 48.55), "tags": {}},
            {"id": 83, "location": (2.60, 48.60), "tags": {}},
        ],
        ways=[
            {"id": 90, "nodes": [81, 82], "tags": {"highway": "path"}},
            {"id": 91, "nodes": [82, 83], "tags": {"highway": "path"}},
        ],
        relations=[
            {
                "id": 900,
                "members": [("r", 901, ""), ("r", 902, "")],
                "tags": {"route": "hiking", "ref": "GR 1", "name": "Tour de test"},
            },
            {"id": 901, "members": [("w", 90, "")], "tags": {"route": "hiking", "ref": "GR 1"}},
            {"id": 902, "members": [("w", 91, "")], "tags": {"route": "hiking", "ref": "GR 1"}},
            {"id": 903, "members": [("w", 90, "")], "tags": {"route": "bicycle"}},
        ],
    )

    return directory


@pytest.fixture
def built_index(extracts_directory: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    index_path = tmp_path / "extract-index.sqlite"
    index = OsmExtractIndex.open_for_writing(index_path)
    try:
        for layer, filename in EXTRACT_FILENAMES.items():
            extract_path = extracts_directory / filename
            feature_count = build_layer(index, layer, extract_path)
            index.commit()
            index.record_layer(layer, feature_count, filename, extract_bbox(extract_path))
    finally:
        index.close()

    monkeypatch.setattr(osm_extract, "default_index_path", lambda: index_path)
    return index_path


def forbid_overpass(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Overpass was called although the local extract has the layer")

    for module in (stations_module, pois_module, landmarks_module, geography_module):
        monkeypatch.setattr(module, "query_overpass", fail)


class TestBuiltLayers:
    def test_indexes_every_layer(self, built_index: Path) -> None:
        index = OsmExtractIndex.open_for_reading(built_index)
        assert index is not None
        try:
            summary = index.layer_summary()
        finally:
            index.close()

        assert set(summary) == set(EXTRACT_FILENAMES)
        assert summary[LAYER_STATIONS]["features"] == 4  # the disused station is dropped
        assert summary[LAYER_TRAILS]["features"] == 3  # the bicycle relation is dropped

    def test_places_a_tagged_way_at_its_bounding_box_center(self, built_index: Path) -> None:
        index = OsmExtractIndex.open_for_reading(built_index)
        assert index is not None
        try:
            elements = index.point_elements(LAYER_ACCOMMODATION, 48.0, 2.0, 49.0, 3.0)["elements"]
        finally:
            index.close()

        camping = next(element for element in elements if element["id"] == 20)
        assert camping["lat"] == pytest.approx(48.42)
        assert camping["lon"] == pytest.approx(2.42)

    def test_keeps_multipolygon_forest_members(self, built_index: Path) -> None:
        index = OsmExtractIndex.open_for_reading(built_index)
        assert index is not None
        try:
            far_forest = index.area_elements(LAYER_FOREST, 45.0, 5.0, 45.3, 5.3)["elements"]
        finally:
            index.close()

        assert [element["id"] for element in far_forest] == [61]

    def test_trusts_extracts_whose_header_declares_no_coverage(self, built_index: Path) -> None:
        """pyosmium writes no header bbox, unlike the Geofabrik extracts."""
        index = OsmExtractIndex.open_for_reading(built_index)
        assert index is not None
        try:
            assert index.layer_summary()[LAYER_STATIONS].get("bbox") is None
            assert index.covers(LAYER_STATIONS, 43.0, 1.0, 43.5, 1.5) is True
        finally:
            index.close()

    def test_ignores_relations_that_are_not_hiking_routes(self, built_index: Path) -> None:
        index = OsmExtractIndex.open_for_reading(built_index)
        assert index is not None
        try:
            assert index.trail_elements(903) is None
            assert index.trail_elements(900) is not None
        finally:
            index.close()


class TestFetchersUseTheIndex:
    def test_fetch_stations_reads_the_index(
        self, built_index: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        forbid_overpass(monkeypatch)
        trail = LineString([(2.50, 48.50), (2.60, 48.60)])

        stations, all_cached = stations_module.fetch_stations(trail)

        assert all_cached is True
        assert sorted(station.name for station in stations) == ["Broye", "Mairie", "Melun"]

    def test_fetch_accommodation_reads_the_index(
        self, built_index: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        forbid_overpass(monkeypatch)
        trail = LineString([(2.40, 48.40), (2.60, 48.60)])

        pois, all_cached = pois_module.fetch_accommodation_pois(trail)

        assert all_cached is True
        assert sorted(poi.name for poi in pois) == ["Camping du Lac", "Hotel"]
        assert sorted(poi.poi_type for poi in pois) == ["camping", "hotel"]

    def test_fetch_landmarks_reads_the_index(
        self, built_index: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        forbid_overpass(monkeypatch)
        trail = LineString([(2.52, 48.52), (2.56, 48.56)])

        found, all_cached = landmarks_module.fetch_landmarks(trail)

        assert all_cached is True
        assert [(landmark.name, landmark.kind, landmark.elevation_m) for landmark in found] == [
            ("Chateau", "castle", 180)
        ]

    def test_fetch_forest_areas_reads_the_index(
        self, built_index: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        forbid_overpass(monkeypatch)

        polygons = geography_module.fetch_forest_areas((2.40, 48.40, 2.70, 48.70))

        assert len(polygons) == 1
        assert polygons[0].bounds == pytest.approx((2.40, 48.40, 2.70, 48.70))

    def test_fetch_trail_builds_the_geometry_from_the_index(
        self, built_index: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("Overpass was called for a relation held locally")

        monkeypatch.setattr("open_rando.fetchers.overpass.query_overpass", fail)

        trail, metadata, cache_hit = fetch_trail(900)

        assert cache_hit is True
        assert metadata == {"name": "Tour de test", "ref": "GR 1", "osm_relation_id": 900}
        assert list(trail.coords) == [
            pytest.approx((2.50, 48.50)),
            pytest.approx((2.55, 48.55)),
            pytest.approx((2.60, 48.60)),
        ]
