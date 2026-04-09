"""Tests for geography module: region resolution and terrain classification."""

from __future__ import annotations

from shapely.geometry import LineString, Polygon

from open_rando.processors.geography import (
    build_sncf_insee_index,
    classify_terrain,
    compute_forest_ratio,
    resolve_departement,
    resolve_region,
)


class TestBuildSncfInseeIndex:
    def test_builds_index_from_records(self) -> None:
        records = [
            {"libellecourt": "ABT", "codeinsee": "60001"},
            {"libellecourt": "PSL", "codeinsee": "75056"},
        ]
        index = build_sncf_insee_index(records)
        assert index == {"ABT": "60001", "PSL": "75056"}

    def test_skips_records_without_trigramme(self) -> None:
        records = [{"codeinsee": "75056"}]
        index = build_sncf_insee_index(records)
        assert index == {}

    def test_skips_records_without_insee(self) -> None:
        records = [{"libellecourt": "PSL"}]
        index = build_sncf_insee_index(records)
        assert index == {}


class TestResolveDepartement:
    def test_standard_departement(self) -> None:
        sncf_insee = {"PSL": "75056"}
        assert resolve_departement("PSL", sncf_insee) == "75"

    def test_corse_departement(self) -> None:
        sncf_insee = {"AJA": "2A004"}
        assert resolve_departement("AJA", sncf_insee) == "2A"

    def test_unknown_station(self) -> None:
        assert resolve_departement("XXX", {}) == ""


class TestResolveRegion:
    def test_known_departement(self) -> None:
        assert resolve_region("75") == "Île-de-France"

    def test_another_region(self) -> None:
        assert resolve_region("64") == "Nouvelle-Aquitaine"

    def test_unknown_departement(self) -> None:
        assert resolve_region("99") == ""


class TestClassifyTerrain:
    def test_coastal(self) -> None:
        tags = classify_terrain(
            max_elevation_meters=80,
            elevation_gain_meters=50,
            distance_km=10,
            departement="29",  # Finistère
            forest_ratio=0.1,
        )
        assert "coastal" in tags
        assert "plains" not in tags

    def test_mountain(self) -> None:
        tags = classify_terrain(
            max_elevation_meters=2500,
            elevation_gain_meters=800,
            distance_km=15,
            departement="73",  # Savoie
            forest_ratio=0.1,
        )
        assert "mountain" in tags
        assert "plains" not in tags

    def test_hills(self) -> None:
        tags = classify_terrain(
            max_elevation_meters=600,
            elevation_gain_meters=200,
            distance_km=12,
            departement="69",
            forest_ratio=0.1,
        )
        assert "hills" in tags

    def test_forest(self) -> None:
        tags = classify_terrain(
            max_elevation_meters=200,
            elevation_gain_meters=50,
            distance_km=10,
            departement="77",
            forest_ratio=0.6,
        )
        assert "forest" in tags

    def test_plains(self) -> None:
        tags = classify_terrain(
            max_elevation_meters=100,
            elevation_gain_meters=20,
            distance_km=10,
            departement="45",  # Loiret (inland)
            forest_ratio=0.1,
        )
        assert "plains" in tags
        assert "coastal" not in tags

    def test_mountain_and_forest(self) -> None:
        tags = classify_terrain(
            max_elevation_meters=1200,
            elevation_gain_meters=600,
            distance_km=15,
            departement="88",  # Vosges
            forest_ratio=0.5,
        )
        assert "mountain" in tags
        assert "forest" in tags


class TestComputeForestRatio:
    def test_no_polygons_returns_zero(self) -> None:
        trail = LineString([(0, 0), (1, 1)])
        assert compute_forest_ratio(trail, []) == 0.0

    def test_trail_fully_in_forest(self) -> None:
        forest = Polygon([(-1, -1), (2, -1), (2, 2), (-1, 2)])
        trail = LineString([(0, 0), (1, 1)])
        ratio = compute_forest_ratio(trail, [forest])
        assert ratio == 1.0

    def test_trail_outside_forest(self) -> None:
        forest = Polygon([(10, 10), (11, 10), (11, 11), (10, 11)])
        trail = LineString([(0, 0), (1, 1)])
        ratio = compute_forest_ratio(trail, [forest])
        assert ratio == 0.0
