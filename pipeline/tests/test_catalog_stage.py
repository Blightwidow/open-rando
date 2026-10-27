from __future__ import annotations

from typing import Any

from open_rando.commands.catalog import build_catalog_entries
from open_rando.exporters.catalog import build_catalog, validate_catalog
from open_rando.exporters.report import build_run_report
from open_rando.models import Track

COUNTS = {
    "train_station": 3,
    "bus_stop": 4,
    "hotel": 2,
    "camping": 1,
    "train_station_with_rail_service": 2,
}


def _track(identifier: str, path_ref: str, relation_id: int) -> Track:
    return Track(
        identifier=identifier,
        slug=path_ref.lower().replace(" ", "-"),
        path_ref=path_ref,
        path_name="Name",
        description="",
        osm_relation_id=relation_id,
        distance_km=10.0,
        elevation_gain_meters=100,
        elevation_loss_meters=90,
        max_elevation_meters=500,
        min_elevation_meters=300,
        bounding_box=(1.0, 2.0, 3.0, 4.0),
        region="R",
        departement="77",
        difficulty="easy",
        is_circular_trail=False,
        terrain=[],
        geojson_path=f"tracks/{identifier}/trail.geojson",
        gpx_path=f"tracks/{identifier}/trail.gpx",
        elevation_path=f"tracks/{identifier}/elevation.json",
        last_updated="2026-10-27",
    )


def _no_image(_track_id: str) -> None:
    return None


class TestBuildCatalogEntries:
    def test_entry_carries_the_poi_counts(self):
        entries, _, _ = build_catalog_entries(
            [_track("a", "GR 1", 1)], {"a": dict(COUNTS)}, {}, _no_image
        )

        assert entries[0]["poi_counts"] == COUNTS

    def test_entries_validate_against_the_catalog_schema(self):
        entries, _, _ = build_catalog_entries(
            [_track("a", "GR 1", 1)], {"a": dict(COUNTS)}, {}, _no_image
        )

        validate_catalog(build_catalog(entries))

    def test_entries_are_sorted_by_path_ref(self):
        tracks = [_track("b", "GR 2", 2), _track("a", "GR 1", 1)]

        entries, _, _ = build_catalog_entries(
            tracks, {"a": dict(COUNTS), "b": dict(COUNTS)}, {}, _no_image
        )

        assert [entry["path_ref"] for entry in entries] == ["GR 1", "GR 2"]

    def test_track_with_fewer_than_two_stations_is_left_out(self):
        few = {**COUNTS, "train_station": 1}

        entries, too_few, unlinked = build_catalog_entries(
            [_track("a", "GR 1", 1)], {"a": few}, {}, _no_image
        )

        assert (entries, too_few, unlinked) == ([], ["GR 1"], [])

    def test_track_without_links_is_reported_as_unlinked(self):
        entries, too_few, unlinked = build_catalog_entries(
            [_track("a", "GR 1", 1)], {}, {}, _no_image
        )

        assert (entries, too_few, unlinked) == ([], [], ["GR 1"])

    def test_image_comes_from_the_previous_catalog_by_relation_id(self):
        entries, _, _ = build_catalog_entries(
            [_track("a", "GR 1", 7)], {"a": dict(COUNTS)}, {7: "images/old.webp"}, _no_image
        )

        assert entries[0]["image_path"] == "images/old.webp"

    def test_image_falls_back_to_the_file_on_disk(self):
        entries, _, _ = build_catalog_entries(
            [_track("a", "GR 1", 7)],
            {"a": dict(COUNTS)},
            {},
            lambda track_id: f"images/{track_id}.webp",
        )

        assert entries[0]["image_path"] == "images/a.webp"

    def test_entry_without_any_image_has_no_image_path(self):
        entries, _, _ = build_catalog_entries(
            [_track("a", "GR 1", 7)], {"a": dict(COUNTS)}, {}, _no_image
        )

        assert "image_path" not in entries[0]


def _legacy_route(train_stations: int) -> dict[str, Any]:
    return {
        "id": "a",
        "path_ref": "GR 1",
        "osm_relation_id": 1,
        "distance_km": 10.0,
        "elevation_gain_m": 100,
        "pois": [{"poi_type": "train_station", "rail_service": None}] * train_stations,
    }


class TestRunReportAcrossTheSplit:
    def test_new_catalog_is_compared_with_a_legacy_catalog_with_embedded_pois(self):
        current = [
            {
                "id": "a",
                "path_ref": "GR 1",
                "osm_relation_id": 1,
                "distance_km": 10.0,
                "elevation_gain_m": 100,
                "poi_counts": {**COUNTS, "train_station": 2},
            }
        ]

        report = build_run_report([_legacy_route(3)], current, failed_route_refs=[])

        assert "GR 1: lost 1 train station(s) (3 -> 2)" in report["warnings"]

    def test_rail_service_coverage_reads_the_counts(self):
        current = [
            {
                "id": "a",
                "path_ref": "GR 1",
                "osm_relation_id": 1,
                "poi_counts": dict(COUNTS),
            }
        ]

        report = build_run_report([], current, failed_route_refs=[])

        assert report["rail_service_coverage"] == {"train_stations": 3, "with_departures": 2}
