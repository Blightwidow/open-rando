from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from open_rando.exporters.catalog import (
    LINKS_SCHEMA_RESOURCE,
    POI_INDEX_SCHEMA_RESOURCE,
    POI_SQUARE_SCHEMA_RESOURCE,
    CatalogValidationError,
    build_catalog,
    export_route_catalog,
    validate_catalog,
    validate_document,
)
from open_rando.exporters.pois import build_poi_index, export_poi_square
from open_rando.models import Landmark, PoiLink, PointOfInterest, RailService, ServiceWindow, Track
from open_rando.poi_grid import PoiGrid

POI_COUNTS = {
    "train_station": 2,
    "bus_stop": 5,
    "hotel": 3,
    "camping": 1,
    "train_station_with_rail_service": 1,
}


def build_track(**overrides: Any) -> Track:
    track = Track(
        identifier="abc123def456",
        slug="gr-1",
        path_ref="GR 1",
        path_name="Tour de l'Ile-de-France",
        description="Boucle autour de Paris",
        osm_relation_id=123456,
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
        geojson_path="tracks/abc123def456/trail.geojson",
        gpx_path="tracks/abc123def456/trail.gpx",
        elevation_path="tracks/abc123def456/elevation.json",
        last_updated="2026-08-18",
        landmarks=[Landmark(name="Chateau", kind="castle", lat=48.5, lon=2.6, elevation_m=180)],
    )
    for name, value in overrides.items():
        setattr(track, name, value)
    return track


def build_entry(**overrides: Any) -> dict[str, Any]:
    entry = build_track().to_dict()
    entry["poi_counts"] = dict(POI_COUNTS)
    entry.update(overrides)
    return entry


class TestValidateCatalog:
    def test_accepts_a_freshly_built_catalog(self) -> None:
        validate_catalog(build_catalog([build_entry()]))

    def test_accepts_a_route_without_optional_fields(self) -> None:
        entry = build_entry()
        del entry["landmarks"]
        validate_catalog(build_catalog([entry]))

    def test_accepts_an_image_path(self) -> None:
        validate_catalog(build_catalog([build_entry(image_path="images/abc123def456.webp")]))

    def test_rejects_embedded_pois(self) -> None:
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([build_entry(pois=[])]))

    def test_rejects_a_route_without_poi_counts(self) -> None:
        entry = build_entry()
        del entry["poi_counts"]
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([entry]))

    def test_rejects_an_unknown_route_field(self) -> None:
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([build_entry(mystery_field="surprise")]))

    def test_rejects_a_missing_required_field(self) -> None:
        entry = build_entry()
        del entry["distance_km"]
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([entry]))

    def test_rejects_an_unknown_difficulty(self) -> None:
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([build_entry(difficulty="extreme")]))

    def test_rejects_a_retyped_field(self) -> None:
        with pytest.raises(CatalogValidationError):
            validate_catalog(build_catalog([build_entry(distance_km="61.2")]))

    def test_names_the_offending_path(self) -> None:
        with pytest.raises(CatalogValidationError, match="routes/0/difficulty"):
            validate_catalog(build_catalog([build_entry(difficulty="extreme")]))


class TestExportRouteCatalog:
    def test_writes_a_valid_catalog(self, tmp_path: Path) -> None:
        output_path = tmp_path / "catalog.json"
        export_route_catalog([build_entry()], str(output_path))

        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written["routes"][0]["path_ref"] == "GR 1"
        assert written["routes"][0]["poi_counts"]["train_station"] == 2

    def test_writes_nothing_when_validation_fails(self, tmp_path: Path) -> None:
        output_path = tmp_path / "catalog.json"
        with pytest.raises(CatalogValidationError):
            export_route_catalog([build_entry(bbox=[1.0, 2.0])], str(output_path))

        assert not output_path.exists()


class TestPoiSquareSchema:
    def _write_square(self, tmp_path: Path, pois: list[PointOfInterest]) -> dict[str, Any]:
        export_poi_square((8, 3), pois, str(tmp_path))
        return json.loads((tmp_path / "8_3.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def test_accepts_what_the_exporter_writes(self, tmp_path: Path) -> None:
        station = PointOfInterest(
            name="Melun",
            lat=48.53,
            lon=2.65,
            poi_type="train_station",
            url="https://example.invalid/melun",
            rail_service=RailService(
                weekday=ServiceWindow(
                    first_departure_minutes=342, last_departure_minutes=1335, departure_count=48
                )
            ),
            osm_id="node/1",
        )
        bus_stop = PointOfInterest(
            name="Mairie",
            lat=48.5,
            lon=2.6,
            poi_type="bus_stop",
            transit_lines=["12"],
            osm_id="node/2",
        )
        hotel = PointOfInterest(name="Hotel", lat=48.5, lon=2.6, poi_type="hotel", osm_id="way/3")

        document = self._write_square(tmp_path, [station, bus_stop, hotel])

        validate_document(document, POI_SQUARE_SCHEMA_RESOURCE)

    def test_rejects_a_poi_without_a_stable_id(self, tmp_path: Path) -> None:
        document = self._write_square(
            tmp_path, [PointOfInterest(name="X", lat=48.5, lon=2.6, poi_type="hotel", osm_id="")]
        )

        with pytest.raises(CatalogValidationError):
            validate_document(document, POI_SQUARE_SCHEMA_RESOURCE)

    def test_rejects_an_unknown_kind(self, tmp_path: Path) -> None:
        document = self._write_square(
            tmp_path,
            [PointOfInterest(name="X", lat=48.5, lon=2.6, poi_type="gite", osm_id="node/1")],
        )

        with pytest.raises(CatalogValidationError):
            validate_document(document, POI_SQUARE_SCHEMA_RESOURCE)

    def test_rejects_a_malformed_rail_service_window(self, tmp_path: Path) -> None:
        station = PointOfInterest(
            name="Melun",
            lat=48.5,
            lon=2.6,
            poi_type="train_station",
            rail_service=RailService(
                weekday=ServiceWindow(
                    first_departure_minutes=1, last_departure_minutes=2, departure_count=0
                )
            ),
            osm_id="node/1",
        )
        document = self._write_square(tmp_path, [station])

        with pytest.raises(CatalogValidationError):
            validate_document(document, POI_SQUARE_SCHEMA_RESOURCE)


class TestPoiIndexSchema:
    def test_accepts_what_the_exporter_builds(self) -> None:
        index = build_poi_index(PoiGrid(), {(8, 3): 12, (0, 0): 0})

        validate_document(index, POI_INDEX_SCHEMA_RESOURCE)

    def test_rejects_a_square_without_a_count(self) -> None:
        index = build_poi_index(PoiGrid(), {(8, 3): 12})
        del index["squares"][0]["count"]  # type: ignore[index]

        with pytest.raises(CatalogValidationError):
            validate_document(index, POI_INDEX_SCHEMA_RESOURCE)


class TestLinksSchema:
    def _document(self) -> dict[str, Any]:
        return {
            "route_id": "abc123def456",
            "counts": dict(POI_COUNTS),
            "links": [
                PoiLink(
                    "node/1", "train_station", 220.0, distance_km=7.85, junction=(5.1, 45.0)
                ).to_dict(),
                PoiLink("way/2", "hotel", 900.5).to_dict(),
            ],
        }

    def test_accepts_what_the_model_writes(self) -> None:
        validate_document(self._document(), LINKS_SCHEMA_RESOURCE)

    def test_rejects_a_negative_distance(self) -> None:
        document = self._document()
        document["links"][0]["distance_to_trail_m"] = -1
        with pytest.raises(CatalogValidationError):
            validate_document(document, LINKS_SCHEMA_RESOURCE)

    def test_rejects_missing_counts(self) -> None:
        document = self._document()
        del document["counts"]
        with pytest.raises(CatalogValidationError):
            validate_document(document, LINKS_SCHEMA_RESOURCE)
