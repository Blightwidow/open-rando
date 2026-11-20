"""What each stage records about its inputs, and how the report receives it."""

from __future__ import annotations

from pathlib import Path

import pytest

from open_rando.exporters import run_inputs
from open_rando.exporters.run_inputs import (
    load_run_inputs,
    osm_inputs,
    record_stage_inputs,
    routing_inputs,
    summarize_inputs_for_log,
)
from open_rando.fetchers.osm_extract import LAYER_STATIONS, OsmExtractIndex
from open_rando.fetchers.osm_source import LocalExtractSource, OverpassSource


@pytest.fixture
def fixed_code_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        run_inputs, "code_version", lambda: {"commit": "abcdef1234567890", "modified": False}
    )


def test_records_a_stage_with_its_inputs(
    isolated_run_inputs: Path, fixed_code_version: None
) -> None:
    record_stage_inputs("link", {"routing": {"osrm_url": "http://localhost:5000"}})

    assert load_run_inputs()["link"]["routing"] == {"osrm_url": "http://localhost:5000"}


def test_records_the_code_version(isolated_run_inputs: Path, fixed_code_version: None) -> None:
    record_stage_inputs("tracks", {})

    assert load_run_inputs()["tracks"]["code_version"]["commit"] == "abcdef1234567890"


def test_keeps_other_stages_when_one_stage_reruns(
    isolated_run_inputs: Path, fixed_code_version: None
) -> None:
    record_stage_inputs("tracks", {"routes": "all"})
    record_stage_inputs("link", {"routes": "all"})
    record_stage_inputs("tracks", {"routes": ["GR 13"]})

    recorded = load_run_inputs()
    assert (recorded["tracks"]["routes"], recorded["link"]["routes"]) == (["GR 13"], "all")


def test_starts_over_when_the_file_is_unreadable(isolated_run_inputs: Path) -> None:
    isolated_run_inputs.write_text("[not an object]", encoding="utf-8")

    assert load_run_inputs() == {}


def test_overpass_source_records_only_its_name() -> None:
    assert osm_inputs(OverpassSource()) == {"source": "overpass"}


def test_local_source_records_index_layers_and_border_fallbacks(tmp_path: Path) -> None:
    index_path = tmp_path / "index.sqlite"
    index = OsmExtractIndex.open_for_writing(index_path)
    index.insert_points(LAYER_STATIONS, [("node", 1, 48.5, 2.5, {"railway": "station"})])
    index.record_layer(LAYER_STATIONS, 1, "stations.osm.pbf")
    index.close()
    source = LocalExtractSource(index_path)
    source.border_fallback_relations.extend([3315112, 2704286])

    recorded = osm_inputs(source)

    assert (
        recorded["index_layers"][LAYER_STATIONS]["source"],
        recorded["border_fallback_relations"],
    ) == ("stations.osm.pbf", [2704286, 3315112])


def test_routing_records_the_router_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_inputs, "OSRM_HOST", "http://localhost:5055")

    assert routing_inputs(walking_refinement=True)["osrm_url"] == "http://localhost:5055"


def test_log_summary_names_each_stage_and_commit() -> None:
    inputs = {
        "tracks": {
            "recorded_at": "2026-11-20T10:00:00+00:00",
            "code_version": {"commit": "abcdef1234567890", "modified": True},
        }
    }

    assert summarize_inputs_for_log(inputs) == [
        "tracks: 2026-11-20T10:00:00+00:00 at abcdef12 (modified)"
    ]


def test_code_version_reads_the_repository_commit() -> None:
    version = run_inputs.code_version()

    assert version["commit"] is None or len(version["commit"]) == 40
