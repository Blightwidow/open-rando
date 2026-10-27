from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import LineString, MultiLineString

from open_rando.commands.tracks import trail_start
from open_rando.exporters.elevation import export_route_elevation
from open_rando.exporters.track import export_track_metadata, load_track_metadata
from open_rando.models import Landmark, Station, Track
from open_rando.processors.elevation import ElevationProfile
from open_rando.processors.geography import resolve_departement_near_point

SNCF_INSEE = {"AAA": "64102", "BBB": "31555", "CCC": "75056"}


def _station(code: str, lat: float, lon: float, transport_type: str = "train") -> Station:
    return Station(name=code, code=code, lat=lat, lon=lon, transport_type=transport_type)


def _track() -> Track:
    return Track(
        identifier="abc123",
        slug="gr-13",
        path_ref="GR 13",
        path_name="Sentier",
        description="desc",
        osm_relation_id=42,
        distance_km=10.5,
        elevation_gain_meters=300,
        elevation_loss_meters=250,
        max_elevation_meters=900,
        min_elevation_meters=400,
        bounding_box=(1.0, 2.0, 3.0, 4.0),
        region="Occitanie",
        departement="31",
        difficulty="moderate",
        is_circular_trail=False,
        terrain=["forest"],
        geojson_path="tracks/abc123/trail.geojson",
        gpx_path="tracks/abc123/trail.gpx",
        elevation_path="tracks/abc123/elevation.json",
        last_updated="2026-10-27",
        landmarks=[Landmark(name="Pic", kind="peak", lat=1.0, lon=2.0, elevation_m=1200)],
        trail_segment_count=2,
        trail_gap_km=0.4,
    )


class TestDepartementNearPoint:
    def test_uses_nearest_sncf_station(self):
        stations = [_station("AAA", 43.0, -0.5), _station("BBB", 43.6, 1.4)]

        departement = resolve_departement_near_point(
            43.55, 1.35, stations, {"AAA", "BBB"}, SNCF_INSEE
        )

        assert departement == "31"

    def test_ignores_stations_outside_sncf_dataset(self):
        stations = [_station("AAA", 43.55, 1.35), _station("BBB", 43.6, 1.4)]

        departement = resolve_departement_near_point(43.55, 1.35, stations, {"BBB"}, SNCF_INSEE)

        assert departement == "31"

    def test_ignores_bus_stops(self):
        stations = [_station("AAA", 43.55, 1.35, transport_type="bus")]

        assert resolve_departement_near_point(43.55, 1.35, stations, {"AAA"}, SNCF_INSEE) == ""

    def test_returns_empty_when_no_station_is_known(self):
        assert resolve_departement_near_point(43.55, 1.35, [], {"AAA"}, SNCF_INSEE) == ""


class TestTrailStart:
    def test_line_start_is_first_vertex(self):
        assert trail_start(LineString([(5.0, 45.0), (6.0, 46.0)])) == (45.0, 5.0)

    def test_multiline_start_is_first_vertex_of_first_segment(self):
        trail = MultiLineString([[(5.0, 45.0), (6.0, 46.0)], [(7.0, 47.0), (8.0, 48.0)]])

        assert trail_start(trail) == (45.0, 5.0)


class TestTrackFiles:
    def test_metadata_round_trips(self, tmp_path: Path):
        export_track_metadata(_track(), tmp_path / "abc123")

        assert load_track_metadata(tmp_path / "abc123") == _track()

    def test_metadata_has_no_pois(self):
        assert "pois" not in _track().to_dict()

    def test_elevation_file_name_is_configurable(self, tmp_path: Path):
        profile = ElevationProfile(
            distances_km=[0.0, 1.0],
            elevations_m=[100.0, 150.0],
            cumulative_times_min=[0.0, 12.0],
            gain_m=50,
            loss_m=0,
            max_m=150,
            min_m=100,
        )

        export_route_elevation(profile, "abc123", str(tmp_path), file_name="elevation.json")

        written = json.loads((tmp_path / "elevation.json").read_text(encoding="utf-8"))
        assert written["distances_km"] == [0.0, 1.0]
