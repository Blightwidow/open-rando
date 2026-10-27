"""`tracks` subcommand — compute each curated GR track on its own.

A track is the trail geometry plus what derives from it (elevation, terrain,
difficulty, landmarks). It knows nothing about POIs: those live in the POI
grid and are joined to a track by the `link` stage.

Output, per track: `tracks/<id>/{track.json, trail.geojson, trail.gpx, elevation.json}`.
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date
from pathlib import Path

from shapely.geometry import LineString, MultiLineString

from open_rando.config import (
    ELEVATION_SAMPLE_INTERVAL_METERS,
    FAILURE_LOG_PATH,
    OVERPASS_COOLDOWN_SECONDS,
    SRTM_BASE_URL,
    SRTM_CACHE_DIRECTORY,
    TRACKS_DIRECTORY,
)
from open_rando.exporters.elevation import export_route_elevation
from open_rando.exporters.failures import (
    build_failure_entry,
    export_failure_log,
    load_failure_log,
)
from open_rando.exporters.geojson import export_route_geojson
from open_rando.exporters.gpx import export_route_gpx
from open_rando.exporters.track import (
    ELEVATION_FILE_NAME,
    TRAIL_GEOJSON_FILE_NAME,
    TRAIL_GPX_FILE_NAME,
    export_track_metadata,
)
from open_rando.fetchers.discovery import discover_routes
from open_rando.fetchers.landmarks import fetch_landmarks
from open_rando.fetchers.sncf import build_sncf_code_set, fetch_sncf_stations
from open_rando.fetchers.srtm import SrtmReader
from open_rando.fetchers.stations import fetch_stations_in_bounds
from open_rando.models import Track, generate_route_id, slugify
from open_rando.processors.elevation import (
    classify_difficulty,
    compute_trail_elevation_profile,
    elevations_for_geometry,
)
from open_rando.processors.geography import (
    build_sncf_insee_index,
    classify_terrain,
    compute_forest_ratio,
    fetch_forest_areas,
    resolve_departement_near_point,
    resolve_region,
)
from open_rando.processors.slice import compute_trail_gaps_km
from open_rando.processors.trail import detect_circular_trail, fetch_and_fuse_trails

logger = logging.getLogger("open_rando")

# The nearest SNCF station to a trail start can be far in the countryside.
DEPARTEMENT_SEARCH_RADIUS_DEGREES = 0.25  # ~25-30 km


def add_tracks_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "tracks",
        help="Compute curated GR tracks (geometry, elevation, terrain), without POIs.",
    )
    parser.add_argument("--route", type=str, help="Process a single route by ref ('GR 13').")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the routes that would be processed.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Only process routes listed in data/failed-routes.json.",
    )
    parser.set_defaults(func=run_tracks)


def trail_start(trail: LineString | MultiLineString) -> tuple[float, float]:
    """(latitude, longitude) of the first vertex of the trail."""
    first_segment = trail.geoms[0] if isinstance(trail, MultiLineString) else trail
    longitude, latitude = first_segment.coords[0][:2]
    return float(latitude), float(longitude)


def build_track(
    relation_ids: list[int],
    route_ref: str,
    route_name: str,
    route_description: str,
    srtm_reader: SrtmReader,
    sncf_codes: set[str],
    sncf_insee: dict[str, str],
    tracks_directory: Path,
) -> tuple[Track, bool]:
    """Compute one track and write its files. Returns (track, all_cached)."""
    trail, trail_metadata, trail_cached = fetch_and_fuse_trails(relation_ids)
    if not trail_cached:
        time.sleep(OVERPASS_COOLDOWN_SECONDS)

    landmarks, landmarks_cached = fetch_landmarks(trail)
    all_cached = trail_cached and landmarks_cached

    path_ref = route_ref or str(trail_metadata["ref"])
    path_name = route_name or str(trail_metadata["name"])
    osm_relation_id = int(trail_metadata["osm_relation_id"])
    track_id = generate_route_id(path_ref, osm_relation_id)

    # Segment by segment, so the gaps between mapped segments are never
    # charged as distance, climb or time.
    profile = compute_trail_elevation_profile(trail, srtm_reader, ELEVATION_SAMPLE_INTERVAL_METERS)

    # GPX carries an elevation per vertex, in trail order.
    if isinstance(trail, MultiLineString):
        all_coordinates: list[tuple[float, ...]] = []
        for segment in trail.geoms:
            all_coordinates.extend(segment.coords)
        vertex_line = LineString(all_coordinates)
    else:
        vertex_line = trail
    vertex_elevations = elevations_for_geometry(vertex_line, srtm_reader)

    total_distance_km = round(profile.distances_km[-1], 1) if profile.distances_km else 0.0
    trail_segment_count = len(trail.geoms) if isinstance(trail, MultiLineString) else 1
    trail_gap_km = round(compute_trail_gaps_km(trail), 2)
    if trail_gap_km >= 1.0:
        logger.warning(
            "  Trail has %d segments with %.1f km of unmapped gaps (not counted as walked)",
            trail_segment_count,
            trail_gap_km,
        )

    trail_bounds = trail.bounds
    start_latitude, start_longitude = trail_start(trail)
    nearby_stations, stations_cached = fetch_stations_in_bounds(
        start_latitude - DEPARTEMENT_SEARCH_RADIUS_DEGREES,
        start_longitude - DEPARTEMENT_SEARCH_RADIUS_DEGREES,
        start_latitude + DEPARTEMENT_SEARCH_RADIUS_DEGREES,
        start_longitude + DEPARTEMENT_SEARCH_RADIUS_DEGREES,
    )
    all_cached = all_cached and stations_cached
    departement = resolve_departement_near_point(
        start_latitude, start_longitude, nearby_stations, sncf_codes, sncf_insee
    )
    region = resolve_region(departement)

    forest_ratio = compute_forest_ratio(trail, fetch_forest_areas(trail_bounds))
    terrain = classify_terrain(
        max_elevation_meters=profile.max_m,
        elevation_gain_meters=profile.gain_m,
        distance_km=total_distance_km,
        departement=departement,
        forest_ratio=forest_ratio,
    )
    difficulty = classify_difficulty(
        gain_m=profile.gain_m,
        loss_m=profile.loss_m,
        distance_km=total_distance_km,
    )

    track_directory = tracks_directory / track_id
    relative_directory = f"tracks/{track_id}"
    export_route_gpx(
        trail=trail,
        name=path_ref,
        description=path_name,
        output_path=str(track_directory / TRAIL_GPX_FILE_NAME),
        elevations=vertex_elevations,
    )
    export_route_geojson(
        trail=trail,
        route_id=track_id,
        name=path_ref,
        output_path=str(track_directory / TRAIL_GEOJSON_FILE_NAME),
    )
    export_route_elevation(
        profile=profile,
        route_id=track_id,
        output_directory=str(track_directory),
        file_name=ELEVATION_FILE_NAME,
    )

    track = Track(
        identifier=track_id,
        slug=slugify(path_ref),
        path_ref=path_ref,
        path_name=path_name,
        description=route_description,
        osm_relation_id=osm_relation_id,
        distance_km=total_distance_km,
        elevation_gain_meters=profile.gain_m,
        elevation_loss_meters=profile.loss_m,
        max_elevation_meters=profile.max_m,
        min_elevation_meters=profile.min_m,
        bounding_box=(
            float(trail_bounds[0]),
            float(trail_bounds[1]),
            float(trail_bounds[2]),
            float(trail_bounds[3]),
        ),
        region=region,
        departement=departement,
        difficulty=difficulty,
        is_circular_trail=detect_circular_trail(trail),
        terrain=terrain,
        geojson_path=f"{relative_directory}/{TRAIL_GEOJSON_FILE_NAME}",
        gpx_path=f"{relative_directory}/{TRAIL_GPX_FILE_NAME}",
        elevation_path=f"{relative_directory}/{ELEVATION_FILE_NAME}",
        last_updated=date.today().isoformat(),
        landmarks=landmarks,
        trail_segment_count=trail_segment_count,
        trail_gap_km=trail_gap_km,
    )
    export_track_metadata(track, track_directory)
    return track, all_cached


def run_tracks(arguments: argparse.Namespace) -> None:
    discovered = discover_routes()

    if arguments.route:
        discovered = [route for route in discovered if route["ref"] == arguments.route]
        if not discovered:
            logger.error("Route '%s' not found in discovered routes", arguments.route)
            return

    failure_log_path = str(Path(FAILURE_LOG_PATH).expanduser())
    failure_log = load_failure_log(failure_log_path)

    if arguments.retry_failed:
        discovered = [route for route in discovered if route["ref"] in failure_log]
        if not discovered:
            logger.info("No failed routes to retry (%s)", failure_log_path)
            return
        logger.info("Retrying %d previously failed route(s)", len(discovered))

    if arguments.dry_run:
        logger.info("Discovered %d routes:", len(discovered))
        for route in discovered:
            logger.info(
                "  %s — %s (relation %d)", route["ref"], route["name"], route["relation_id"]
            )
        return

    tracks_directory = Path(TRACKS_DIRECTORY).expanduser()
    tracks_directory.mkdir(parents=True, exist_ok=True)

    srtm_reader = SrtmReader(
        cache_directory=str(Path(SRTM_CACHE_DIRECTORY).expanduser()),
        base_url=SRTM_BASE_URL,
    )
    sncf_records = fetch_sncf_stations()
    sncf_codes = build_sncf_code_set(sncf_records)
    sncf_insee = build_sncf_insee_index(sncf_records)

    succeeded = 0
    failed: list[str] = []
    previous_used_api = False

    for route_index, discovered_route in enumerate(discovered):
        route_ref = str(discovered_route["ref"])
        relation_ids = [
            int(relation_id)
            for relation_id in discovered_route.get(
                "relation_ids", [discovered_route["relation_id"]]
            )
        ]
        if route_index > 0 and previous_used_api:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)

        logger.info(
            "=== [%d/%d] Track %s (relations: %s) ===",
            route_index + 1,
            len(discovered),
            route_ref,
            ", ".join(str(relation_id) for relation_id in relation_ids),
        )
        try:
            track, all_cached = build_track(
                relation_ids=relation_ids,
                route_ref=route_ref,
                route_name=str(discovered_route.get("name", "")),
                route_description=str(discovered_route.get("description", "")),
                srtm_reader=srtm_reader,
                sncf_codes=sncf_codes,
                sncf_insee=sncf_insee,
                tracks_directory=tracks_directory,
            )
            logger.info(
                "  -> %s: %.1f km, +%d m, %s",
                track.path_ref,
                track.distance_km,
                track.elevation_gain_meters,
                track.difficulty,
            )
            succeeded += 1
            previous_used_api = not all_cached
            if failure_log.pop(route_ref, None) is not None:
                export_failure_log(failure_log, failure_log_path)
        except Exception as error:
            logger.exception("Failed to process %s, skipping", route_ref)
            failed.append(route_ref)
            previous_used_api = True
            failure_log[route_ref] = build_failure_entry(
                route_ref=route_ref,
                relation_ids=relation_ids,
                error=error,
                previous_entry=failure_log.get(route_ref),
            )
            export_failure_log(failure_log, failure_log_path)

    logger.info("=== Summary: %d/%d tracks computed ===", succeeded, len(discovered))
    if failed:
        logger.warning("Failed: %s — rerun with --retry-failed", ", ".join(failed))
