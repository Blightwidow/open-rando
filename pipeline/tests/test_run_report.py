from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from open_rando.exporters.report import build_run_report, export_run_report

GENERATED_AT = "2026-08-18T00:00:00+00:00"


def build_route_dict(
    path_ref: str = "GR 1",
    relation_id: int = 111,
    distance_km: float = 60.0,
    train_stations: int = 4,
    bus_stops: int = 2,
    hotels: int = 1,
    campings: int = 1,
    elevation_gain_m: int = 900,
    stations_with_rail_service: int = 0,
    trail_gap_km: float = 0.0,
) -> dict[str, Any]:
    pois: list[dict[str, Any]] = []
    for index in range(train_stations):
        station: dict[str, Any] = {"name": f"Gare {index}", "poi_type": "train_station"}
        if index < stations_with_rail_service:
            station["rail_service"] = {
                "weekday": {
                    "first_departure_minutes": 342,
                    "last_departure_minutes": 1335,
                    "departure_count": 20,
                },
                "saturday": None,
                "sunday": None,
            }
        pois.append(station)
    pois.extend({"name": f"Arret {index}", "poi_type": "bus_stop"} for index in range(bus_stops))
    pois.extend({"name": f"Hotel {index}", "poi_type": "hotel"} for index in range(hotels))
    pois.extend({"name": f"Camping {index}", "poi_type": "camping"} for index in range(campings))

    return {
        "id": f"id-{relation_id}",
        "path_ref": path_ref,
        "osm_relation_id": relation_id,
        "distance_km": distance_km,
        "elevation_gain_m": elevation_gain_m,
        "trail_gap_km": trail_gap_km,
        "pois": pois,
    }


class TestBuildRunReport:
    def test_reports_added_routes(self) -> None:
        report = build_run_report(
            previous_routes=[],
            current_routes=[build_route_dict()],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["routes_added"] == ["GR 1"]
        assert report["routes_total"] == 1
        assert report["warnings"] == []

    def test_reports_a_route_that_disappeared(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict()],
            current_routes=[],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["routes_removed"] == ["GR 1"]
        assert report["warnings"] == ["GR 1: disappeared from the catalog"]

    def test_counts_untouched_routes_as_unchanged(self) -> None:
        route = build_route_dict()
        report = build_run_report(
            previous_routes=[route],
            current_routes=[build_route_dict()],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["routes_unchanged"] == 1
        assert report["routes_changed"] == []

    def test_matches_routes_on_relation_id_not_name(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict(path_ref="GR 1")],
            current_routes=[build_route_dict(path_ref="GR 1 renamed")],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["routes_added"] == []
        assert report["routes_removed"] == []
        assert report["routes_unchanged"] == 1

    def test_warns_when_a_route_shrinks(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict(distance_km=60.0)],
            current_routes=[build_route_dict(distance_km=40.0)],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["warnings"] == ["GR 1: distance dropped 33% (60.0 -> 40.0 km)"]

    def test_ignores_a_small_distance_change(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict(distance_km=60.0)],
            current_routes=[build_route_dict(distance_km=59.0)],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["warnings"] == []
        assert len(report["routes_changed"]) == 1

    def test_warns_when_train_stations_are_lost(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict(train_stations=6)],
            current_routes=[build_route_dict(train_stations=4)],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["warnings"] == ["GR 1: lost 2 train station(s) (6 -> 4)"]

    def test_warns_when_elevation_gain_collapses(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict(elevation_gain_m=1000)],
            current_routes=[build_route_dict(elevation_gain_m=500)],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["warnings"] == ["GR 1: elevation gain dropped 50% (1000 -> 500 m)"]

    def test_records_failed_and_skipped_routes(self) -> None:
        report = build_run_report(
            previous_routes=[],
            current_routes=[],
            failed_route_refs=["GR 20"],
            skipped_route_refs=["GR 5"],
            generated_at=GENERATED_AT,
        )

        assert report["failed_routes"] == ["GR 20"]
        assert report["skipped_routes"] == ["GR 5"]

    def test_warns_when_stations_lose_their_departures(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict(train_stations=3, stations_with_rail_service=3)],
            current_routes=[build_route_dict(train_stations=3, stations_with_rail_service=1)],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["warnings"] == ["GR 1: 2 station(s) lost their train departures (3 -> 1)"]

    def test_warns_when_unmapped_gaps_grow(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict(trail_gap_km=0.5)],
            current_routes=[build_route_dict(trail_gap_km=18.1)],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["warnings"] == ["GR 1: unmapped gaps grew by 17.6 km (0.5 -> 18.1 km)"]

    def test_ignores_a_small_gap_change(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict(trail_gap_km=0.5)],
            current_routes=[build_route_dict(trail_gap_km=1.2)],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["warnings"] == []

    def test_reports_rail_service_coverage(self) -> None:
        report = build_run_report(
            previous_routes=[],
            current_routes=[build_route_dict(train_stations=4, stations_with_rail_service=3)],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        assert report["rail_service_coverage"] == {"train_stations": 4, "with_departures": 3}

    def test_details_the_change_for_each_route(self) -> None:
        report = build_run_report(
            previous_routes=[build_route_dict(bus_stops=2)],
            current_routes=[build_route_dict(bus_stops=7)],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        [change] = report["routes_changed"]
        assert change["bus_stops"] == {"before": 2, "after": 7}
        assert change["stations_with_rail_service"] == {"before": 0, "after": 0}
        assert change["path_ref"] == "GR 1"


class TestExportRunReport:
    def test_writes_the_report_as_json(self, tmp_path: Path) -> None:
        output_path = tmp_path / "run-report.json"
        report = build_run_report(
            previous_routes=[],
            current_routes=[build_route_dict()],
            failed_route_refs=[],
            generated_at=GENERATED_AT,
        )

        export_run_report(report, str(output_path))

        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written["generated_at"] == GENERATED_AT
        assert written["routes_added"] == ["GR 1"]
