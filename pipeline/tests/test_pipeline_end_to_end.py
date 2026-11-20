"""Run the stages as the CLI does, on a synthetic extract, and check the hand-offs.

See `end_to_end_fixture.py` for what the dataset holds and which stages run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from open_rando.exporters.catalog import load_schema
from tests.end_to_end_fixture import ROUTE_REF, build_fixture_data

pytest.importorskip("osmium")


@pytest.fixture(scope="module")
def data_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_fixture_data(tmp_path_factory.mktemp("end-to-end"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def catalog_route(data_directory: Path) -> dict[str, Any]:
    routes = read_json(data_directory / "catalog.json")["routes"]
    assert len(routes) == 1
    route: dict[str, Any] = routes[0]
    return route


def test_catalog_holds_the_route(data_directory: Path) -> None:
    assert catalog_route(data_directory)["path_ref"] == ROUTE_REF


def test_catalog_counts_both_train_stations(data_directory: Path) -> None:
    assert catalog_route(data_directory)["poi_counts"]["train_station"] == 2


def test_catalog_counts_linked_accommodation_and_resupply(data_directory: Path) -> None:
    counts = catalog_route(data_directory)["poi_counts"]

    assert (counts["hotel"], counts["shop"], counts["bus_stop"]) == (1, 1, 1)


def test_track_elevation_comes_from_the_srtm_tile(data_directory: Path) -> None:
    # The seeded tile is lower to the north and the trail heads north: it only descends.
    route = catalog_route(data_directory)

    assert route["elevation_loss_m"] > 0


def test_links_validate_against_their_schema(data_directory: Path) -> None:
    route_id = catalog_route(data_directory)["id"]
    links = read_json(data_directory / "links" / f"{route_id}.json")

    assert list(Draft202012Validator(load_schema("links.schema.json")).iter_errors(links)) == []


def test_track_files_the_website_serves_exist(data_directory: Path) -> None:
    route = catalog_route(data_directory)

    missing = [
        route[key]
        for key in ("geojson_path", "gpx_path", "elevation_path")
        if not (data_directory / route[key]).exists()
    ]
    assert missing == []


def test_run_report_names_the_inputs_of_every_stage(data_directory: Path) -> None:
    inputs = read_json(data_directory / "run-report.json")["inputs"]

    assert sorted(inputs) == ["link", "pois", "tracks"]


def test_run_report_records_the_local_extract_as_osm_source(data_directory: Path) -> None:
    inputs = read_json(data_directory / "run-report.json")["inputs"]

    assert inputs["tracks"]["osm"]["source"] == "local-extract"
