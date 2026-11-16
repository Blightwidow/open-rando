"""Tests for overlay_features: which OSM features reach which overlay layer."""

from __future__ import annotations

import json

import overlay_features
from overlay_features import centroid, classify, parse_elevation, split_features


def point(**tags: str) -> dict:
    return {
        "type": "Feature",
        "properties": tags,
        "geometry": {"type": "Point", "coordinates": [6.0, 45.0]},
    }


def square(**tags: str) -> dict:
    ring = [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]
    return {
        "type": "Feature",
        "properties": tags,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def line(**tags: str) -> dict:
    return {
        "type": "Feature",
        "properties": tags,
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]},
    }


def layer_of(feature: dict) -> str | None:
    classified = classify(feature)
    return classified[0] if classified else None


class TestClassify:
    def test_drinking_water_goes_to_water_layer(self):
        assert layer_of(point(amenity="drinking_water")) == "water"

    def test_water_tagged_not_drinkable_is_dropped(self):
        assert layer_of(point(amenity="drinking_water", drinking_water="no")) is None

    def test_bus_shelter_is_dropped(self):
        assert layer_of(point(amenity="shelter", shelter_type="public_transport")) is None

    def test_untyped_shelter_is_kept(self):
        assert layer_of(point(amenity="shelter")) == "shelter"

    def test_basic_hut_shelter_is_kept(self):
        assert layer_of(point(amenity="shelter", shelter_type="basic_hut")) == "shelter"

    def test_alpine_hut_also_tagged_shelter_stays_a_hut(self):
        assert layer_of(point(tourism="alpine_hut", amenity="shelter")) == "hut"

    def test_power_line_needs_a_line_geometry(self):
        assert layer_of(point(power="line")) is None

    def test_power_line_goes_to_power_line_layer(self):
        assert layer_of(line(power="line")) == "power_line"

    def test_stream_goes_to_stream_layer(self):
        assert layer_of(line(waterway="stream")) == "stream"

    def test_unrelated_feature_is_dropped(self):
        assert layer_of(point(amenity="cafe")) is None

    def test_peak_keeps_name_and_elevation_only(self):
        _, feature = classify(point(natural="peak", name="Mont Blanc", ele="4806", source="x"))
        assert feature["properties"] == {"name": "Mont Blanc", "ele": 4806}

    def test_peak_with_unreadable_elevation_keeps_the_peak(self):
        _, feature = classify(point(natural="peak", name="Sommet", ele="high"))
        assert feature["properties"] == {"name": "Sommet"}

    def test_shelter_building_becomes_a_point(self):
        _, feature = classify(square(amenity="shelter"))
        assert feature["geometry"] == {"type": "Point", "coordinates": [1.0, 1.0]}

    def test_spring_mapped_as_an_area_is_dropped(self):
        assert layer_of(square(natural="spring")) is None


class TestParseElevation:
    def test_plain_number(self):
        assert parse_elevation("1234") == 1234

    def test_decimal_comma_rounds(self):
        assert parse_elevation("1234,6") == 1235

    def test_unit_suffix_is_ignored(self):
        assert parse_elevation("2100 m") == 2100

    def test_out_of_range_is_rejected(self):
        assert parse_elevation("48060") is None

    def test_missing_is_none(self):
        assert parse_elevation(None) is None


class TestCentroid:
    def test_closed_ring_ignores_the_repeated_first_vertex(self):
        geometry = square()["geometry"]
        assert centroid(geometry)["coordinates"] == [1.0, 1.0]


class TestSplitFeatures:
    def test_writes_only_the_requested_layers(self, tmp_path):
        lines = [
            "\x1e" + json.dumps(point(amenity="drinking_water")),
            json.dumps(point(natural="spring")),
        ]

        counts = split_features(lines, tmp_path, ["water"])

        assert counts == {"water": 1}
        assert not (tmp_path / "spring.geojsonl").exists()

    def test_leaves_other_layers_files_untouched(self, tmp_path):
        (tmp_path / "river.geojsonl").write_text("keep\n")

        split_features([], tmp_path, ["water"])

        assert (tmp_path / "river.geojsonl").read_text() == "keep\n"

    def test_every_rule_layer_is_listed(self):
        assert set(overlay_features.LAYERS) == {rule[0] for rule in overlay_features.RULES}
