"""Which OSM source a run reads, and how each source answers."""

from __future__ import annotations

from pathlib import Path

import pytest

from open_rando.fetchers import osm_extract, osm_source
from open_rando.fetchers.osm_extract import LAYER_STATIONS, LAYER_TRAILS, OsmExtractIndex
from open_rando.fetchers.osm_source import (
    ALLOW_OVERPASS_ENVIRONMENT_VARIABLE,
    LocalExtractSource,
    OsmSourceUnavailableError,
    OverpassSource,
    get_osm_source,
)
from open_rando.json_types import JsonObject
from open_rando.osm_tags import LANDMARK_KINDS_BY_KEY


def build_index(path: Path) -> Path:
    index = OsmExtractIndex.open_for_writing(path)
    index.insert_points(LAYER_STATIONS, [("node", 1, 48.5, 2.5, {"railway": "station"})])
    index.record_layer(LAYER_STATIONS, 1, "stations.osm.pbf")
    index.insert_trail_relations([(900, {"route": "hiking"}, [])])
    index.record_layer(LAYER_TRAILS, 1, "trails.osm.pbf")
    index.commit()
    index.close()
    return path


@pytest.fixture
def index_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = build_index(tmp_path / "index.sqlite")
    monkeypatch.setattr(osm_extract, "default_index_path", lambda: path)
    return path


@pytest.fixture
def no_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(osm_extract, "default_index_path", lambda: tmp_path / "missing.sqlite")


def record_overpass_queries(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    queries: list[str] = []

    def fake_query_overpass(
        query: str, cache_ttl_seconds: int | None = None
    ) -> tuple[JsonObject, bool]:
        queries.append(query)
        return {"elements": []}, False

    monkeypatch.setattr(osm_source, "query_overpass", fake_query_overpass)
    return queries


class TestSourceSelection:
    def test_reads_the_local_index_when_it_exists(self, index_path: Path) -> None:
        assert isinstance(get_osm_source(), LocalExtractSource)

    def test_refuses_to_run_without_an_index(
        self, no_index: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(ALLOW_OVERPASS_ENVIRONMENT_VARIABLE, raising=False)

        with pytest.raises(OsmSourceUnavailableError, match="Makefile.osm"):
            get_osm_source()

    def test_reads_overpass_without_an_index_when_allowed(
        self, no_index: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ALLOW_OVERPASS_ENVIRONMENT_VARIABLE, "1")

        assert isinstance(get_osm_source(), OverpassSource)

    def test_prefers_the_index_even_when_overpass_is_allowed(
        self, index_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ALLOW_OVERPASS_ENVIRONMENT_VARIABLE, "1")

        assert isinstance(get_osm_source(), LocalExtractSource)


class TestLocalExtractSource:
    def test_answers_from_the_index_without_calling_overpass(
        self, index_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        queries = record_overpass_queries(monkeypatch)

        data, cache_hit = LocalExtractSource(index_path).stations((48.0, 2.0, 49.0, 3.0))

        assert [element["id"] for element in data["elements"]] == [1]
        assert cache_hit is True
        assert queries == []

    def test_refuses_a_layer_that_was_not_built(self, index_path: Path) -> None:
        with pytest.raises(OsmSourceUnavailableError, match="landmarks"):
            LocalExtractSource(index_path).landmarks((48.0, 2.0, 49.0, 3.0))

    def test_fetches_a_relation_missing_from_the_extract_from_overpass(
        self, index_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        queries = record_overpass_queries(monkeypatch)
        source = LocalExtractSource(index_path)

        source.trail(2704286)

        assert "rel(2704286)" in queries[0]

    def test_records_relations_fetched_from_overpass(
        self, index_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_overpass_queries(monkeypatch)
        source = LocalExtractSource(index_path)

        source.trail(2704286)

        assert source.border_fallback_relations == [2704286]


class TestOverpassSource:
    def test_landmark_query_selects_every_landmark_kind(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        queries = record_overpass_queries(monkeypatch)

        OverpassSource().landmarks((48.0, 2.0, 49.0, 3.0))

        expected = {
            f'node["{key}"="{kind}"](48.0,2.0,49.0,3.0)'
            for key, kinds in LANDMARK_KINDS_BY_KEY
            for kind in kinds
        }
        assert all(selector in queries[0] for selector in expected)

    def test_forest_query_selects_ways_and_relations(self, monkeypatch: pytest.MonkeyPatch) -> None:
        queries = record_overpass_queries(monkeypatch)

        OverpassSource().forest((48.0, 2.0, 49.0, 3.0))

        assert 'rel["landuse"="forest"](48.0,2.0,49.0,3.0)' in queries[0]
