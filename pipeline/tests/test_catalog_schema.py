from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from open_rando.exporters.catalog import (
    CatalogValidationError,
    build_catalog,
    export_route_catalog,
    validate_catalog,
)
from open_rando.models import PointOfInterest, RailService, Route, ServiceWindow


def build_route(**overrides: Any) -> Route:
    route = Route(
        identifier="abc123def456",
        slug="gr-1",
        path_ref="GR 1",
        path_name="Tour de l'Ile-de-France",
        description="Boucle autour de Paris",
        osm_relation_id=123456,
        pois=[
            PointOfInterest(
                name="Melun",
                lat=48.53,
                lon=2.65,
                poi_type="train_station",
                url="https://example.invalid/melun",
                distance_km=12.5,
                rail_service=RailService(
                    weekday=ServiceWindow(
                        first_departure_minutes=342,
                        last_departure_minutes=1335,
                        departure_count=48,
                    ),
                    saturday=ServiceWindow(
                        first_departure_minutes=400,
                        last_departure_minutes=1450,
                        departure_count=30,
                    ),
                ),
            )
        ],
        distance_km=61.2,
        elevation_gain_meters=820,
        elevation_loss_meters=790,
        max_elevation_meters=210,
        min_elevation_meters=35,
        bounding_box=(2.1, 48.4, 2.9, 48.9),
        region="Ile-de-France",
        departement="77",
        difficulty="moderate",
        is_circular_trail=False,
        terrain=["forest"],
        geojson_path="geojson/abc123def456.json",
        gpx_path="gpx/abc123def456.gpx",
        last_updated="2026-08-18",
    )
    for name, value in overrides.items():
        setattr(route, name, value)
    return route


class TestValidateCatalog:
    def test_accepts_a_freshly_built_catalog(self) -> None:
        validate_catalog(build_catalog([build_route()]))

    def test_accepts_a_station_without_rail_service(self) -> None:
        route = build_route()
        route.pois[0].rail_service = None
        validate_catalog(build_catalog([route]))

    def test_accepts_a_legacy_route_without_optional_fields(self) -> None:
        legacy = build_route().to_dict()
        del legacy["image_path"]
        del legacy["landmarks"]
        del legacy["pois"][0]["rail_service"]
        validate_catalog(build_catalog([legacy]))

    def test_rejects_an_unknown_route_field(self) -> None:
        entry = build_route().to_dict()
        entry["mystery_field"] = "surprise"
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([entry]))

    def test_rejects_a_missing_required_field(self) -> None:
        entry = build_route().to_dict()
        del entry["distance_km"]
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([entry]))

    def test_rejects_an_unknown_difficulty(self) -> None:
        entry = build_route().to_dict()
        entry["difficulty"] = "extreme"
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([entry]))

    def test_rejects_a_retyped_field(self) -> None:
        entry = build_route().to_dict()
        entry["distance_km"] = "61.2"
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([entry]))

    def test_rejects_an_unknown_poi_type(self) -> None:
        entry = build_route().to_dict()
        entry["pois"][0]["poi_type"] = "gite"
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([entry]))

    def test_rejects_a_malformed_rail_service_window(self) -> None:
        entry = build_route().to_dict()
        entry["pois"][0]["rail_service"]["weekday"]["departure_count"] = 0
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([entry]))

    def test_names_the_offending_path(self) -> None:
        entry = build_route().to_dict()
        entry["difficulty"] = "extreme"
        with pytest.raises(CatalogValidationError, match="routes/0/difficulty"):
            validate_catalog(build_catalog([entry]))


class TestExportRouteCatalog:
    def test_writes_a_valid_catalog(self, tmp_path: Path) -> None:
        output_path = tmp_path / "catalog.json"
        export_route_catalog([build_route()], str(output_path))

        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written["routes"][0]["path_ref"] == "GR 1"
        assert written["routes"][0]["pois"][0]["rail_service"]["weekday"]["departure_count"] == 48

    def test_writes_nothing_when_validation_fails(self, tmp_path: Path) -> None:
        output_path = tmp_path / "catalog.json"
        broken = build_route().to_dict()
        broken["bbox"] = [1.0, 2.0]

        with pytest.raises(CatalogValidationError):
            export_route_catalog([broken], str(output_path))

        assert not output_path.exists()
