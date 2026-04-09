from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union

from open_rando.config import (
    CATALOG_PATH,
    CONNECTOR_SKIP_THRESHOLD_METERS,
    ELEVATION_DIRECTORY,
    ELEVATION_SAMPLE_INTERVAL_METERS,
    GEOJSON_DIRECTORY,
    GPX_DIRECTORY,
    MAX_STATION_DISTANCE_METERS,
    MAX_STEP_DISTANCE_KM,
    MIN_STEP_DISTANCE_KM,
    OUTPUT_DIRECTORY,
    OVERPASS_COOLDOWN_SECONDS,
    SRTM_BASE_URL,
    SRTM_CACHE_DIRECTORY,
)
from open_rando.exporters.catalog import export_catalog
from open_rando.exporters.elevation import export_elevation_profile
from open_rando.exporters.geojson import export_geojson
from open_rando.exporters.gpx import export_gpx
from open_rando.fetchers.accommodation import fetch_accommodation
from open_rando.fetchers.discovery import discover_routes
from open_rando.fetchers.overpass import fetch_trail
from open_rando.fetchers.sncf import build_sncf_code_set, fetch_sncf_stations
from open_rando.fetchers.srtm import SrtmReader
from open_rando.fetchers.stations import fetch_stations, filter_stations_by_sncf
from open_rando.models import Hike, HikeStep, Station, generate_hike_id, slugify
from open_rando.processors.connectors import attach_connectors
from open_rando.processors.elevation import (
    classify_difficulty,
    compute_elevation_profile,
    elevations_for_geometry,
    estimate_duration,
)
from open_rando.processors.match import MatchedStation, match_stations_to_trail
from open_rando.processors.slice import find_hikes, find_round_trip_hikes

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("open_rando")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate hiking catalog from GR and PR paths")
    parser.add_argument(
        "--route",
        type=str,
        help="Process a single route by ref (e.g. 'GR 13').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List discovered routes without processing them.",
    )
    parser.add_argument(
        "--type",
        choices=["gr", "pr", "all"],
        default="all",
        help="Which route types to discover and process (default: all).",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Load existing catalog and skip routes already present. New hikes are appended.",
    )
    arguments = parser.parse_args()

    if arguments.type == "gr":
        route_types: list[str] | None = ["gr", "grp"]
    elif arguments.type == "pr":
        route_types = ["pr"]
    else:
        route_types = None

    routes = discover_routes(route_types=route_types)

    if arguments.route:
        routes = [route for route in routes if route["ref"] == arguments.route]
        if not routes:
            logger.error("Route '%s' not found in discovered routes", arguments.route)
            return

    if arguments.dry_run:
        logger.info("Discovered %d routes:", len(routes))
        for route in routes:
            route_type = str(route["route_type"])
            type_marker = f" ({route_type.upper()})" if route_type != "gr" else ""
            logger.info(
                "  %s — %s (relation %d)%s",
                route["ref"],
                route["name"],
                route["relation_id"],
                type_marker,
            )
        return

    Path(GPX_DIRECTORY).expanduser().mkdir(parents=True, exist_ok=True)
    Path(GEOJSON_DIRECTORY).expanduser().mkdir(parents=True, exist_ok=True)
    Path(ELEVATION_DIRECTORY).expanduser().mkdir(parents=True, exist_ok=True)

    srtm_reader = SrtmReader(
        cache_directory=str(Path(SRTM_CACHE_DIRECTORY).expanduser()),
        base_url=SRTM_BASE_URL,
    )

    sncf_records = fetch_sncf_stations()
    sncf_codes = build_sncf_code_set(sncf_records)
    if sncf_codes:
        logger.info("Loaded %d SNCF station codes for filtering", len(sncf_codes))

    # Cross-route station accommodation registry
    accommodation_registry: dict[str, Station] = {}

    all_hikes: list[Hike] = []
    successful_routes = 0
    failed_routes: list[str] = []
    catalog_path = str(Path(CATALOG_PATH).expanduser())

    existing_hike_dicts: list[dict[str, Any]] = []
    existing_relation_ids: set[int] = set()
    if arguments.keep_existing and Path(catalog_path).exists():
        with open(catalog_path, encoding="utf-8") as catalog_file:
            existing_catalog = json.load(catalog_file)
        existing_hike_dicts = existing_catalog.get("hikes", [])
        existing_relation_ids = {int(hike["osm_relation_id"]) for hike in existing_hike_dicts}
        logger.info(
            "Loaded %d existing hikes from catalog (%d routes)",
            len(existing_hike_dicts),
            len(existing_relation_ids),
        )

    previous_route_used_api = False

    for route_index, route in enumerate(routes):
        route_ref = str(route["ref"])
        route_relation_id = int(route["relation_id"])
        route_type = str(route["route_type"])

        if route_relation_id in existing_relation_ids:
            logger.info(
                "  Skipping %s (relation %d) — already in catalog",
                route_ref,
                route_relation_id,
            )
            continue

        if route_index > 0 and previous_route_used_api:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)

        logger.info(
            "=== [%d/%d] Processing %s (relation %d) ===",
            route_index + 1,
            len(routes),
            route_ref,
            route_relation_id,
        )

        try:
            hikes, all_cached = _process_route(
                relation_id=route_relation_id,
                route_type=route_type,
                srtm_reader=srtm_reader,
                accommodation_registry=accommodation_registry,
                sncf_codes=sncf_codes,
            )
            all_hikes.extend(hikes)
            successful_routes += 1
            previous_route_used_api = not all_cached
            logger.info("  -> %d hikes for %s", len(hikes), route_ref)
        except Exception:
            logger.exception("Failed to process %s, skipping", route_ref)
            failed_routes.append(route_ref)
            previous_route_used_api = True

        export_catalog(existing_hike_dicts + all_hikes, catalog_path)

    logger.info("=== Summary ===")
    logger.info("Routes processed: %d/%d", successful_routes, len(routes))
    logger.info(
        "Total hikes: %d (%d existing + %d new)",
        len(existing_hike_dicts) + len(all_hikes),
        len(existing_hike_dicts),
        len(all_hikes),
    )
    logger.info("Catalog written to %s", catalog_path)
    if failed_routes:
        logger.warning("Failed routes: %s", ", ".join(failed_routes))


def _process_route(
    relation_id: int,
    route_type: str,
    srtm_reader: SrtmReader,
    accommodation_registry: dict[str, Station],
    sncf_codes: set[str],
) -> tuple[list[Hike], bool]:
    """Process a single route end-to-end and return generated hikes."""
    trail, trail_metadata, trail_cached = fetch_trail(relation_id)

    if not trail_cached:
        time.sleep(OVERPASS_COOLDOWN_SECONDS)

    stations, stations_cached = fetch_stations(trail)

    if sncf_codes:
        stations = filter_stations_by_sncf(stations, sncf_codes)

    matched = match_stations_to_trail(stations, trail, MAX_STATION_DISTANCE_METERS)
    all_cached = trail_cached and stations_cached

    if len(matched) < 2:
        logger.warning("Only %d stations matched, skipping route", len(matched))
        return [], all_cached

    # Cross-route station dedup: skip accommodation fetch for already-enriched stations
    matched_stations = [station for station, _fraction, _junction in matched]
    stations_needing_accommodation = [
        station for station in matched_stations if station.code not in accommodation_registry
    ]

    if stations_needing_accommodation:
        if not stations_cached:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)
        accommodation_cached = fetch_accommodation(stations_needing_accommodation)
        for station in stations_needing_accommodation:
            accommodation_registry[station.code] = station
    else:
        accommodation_cached = True
        logger.info("All %d stations already have accommodation data", len(matched_stations))

    # Copy accommodation from registry for stations we skipped
    for station in matched_stations:
        already_registered = accommodation_registry.get(station.code)
        if already_registered is not None and station is not already_registered:
            station.accommodation = already_registered.accommodation

    is_circular = _detect_circular_trail(trail)

    raw_hikes = find_hikes(trail, matched, MIN_STEP_DISTANCE_KM, MAX_STEP_DISTANCE_KM)
    logger.info("Found %d hikes", len(raw_hikes))

    round_trip_raw: list[list[tuple[Station, Station, LineString, float]]] = []
    if is_circular:
        round_trip_raw = find_round_trip_hikes(
            trail, matched, MIN_STEP_DISTANCE_KM, MAX_STEP_DISTANCE_KM
        )
        logger.info("Found %d round-trip hikes", len(round_trip_raw))

    path_ref = str(trail_metadata["ref"])
    path_name = str(trail_metadata["name"])
    osm_relation_id = int(trail_metadata["osm_relation_id"])

    hikes: list[Hike] = []
    for raw_steps in raw_hikes:
        hike = _build_hike(
            raw_steps=raw_steps,
            matched_stations=matched,
            path_ref=path_ref,
            path_name=path_name,
            osm_relation_id=osm_relation_id,
            route_type=route_type,
            is_circular=is_circular,
            is_round_trip=False,
            srtm_reader=srtm_reader,
        )
        hikes.append(hike)
    for raw_steps in round_trip_raw:
        hike = _build_hike(
            raw_steps=raw_steps,
            matched_stations=matched,
            path_ref=path_ref,
            path_name=path_name,
            osm_relation_id=osm_relation_id,
            route_type=route_type,
            is_circular=is_circular,
            is_round_trip=True,
            srtm_reader=srtm_reader,
        )
        hikes.append(hike)

    all_cached = all_cached and accommodation_cached
    return hikes, all_cached


def _detect_circular_trail(trail: LineString | MultiLineString) -> bool:
    """Detect if a trail is circular (first and last points within threshold)."""
    if isinstance(trail, MultiLineString):
        segments = list(trail.geoms)
        first_point = segments[0].coords[0]
        last_point = segments[-1].coords[-1]
    else:
        first_point = trail.coords[0]
        last_point = trail.coords[-1]

    # ~1km threshold in degrees
    distance = (
        (first_point[0] - last_point[0]) ** 2 + (first_point[1] - last_point[1]) ** 2
    ) ** 0.5
    is_circular: bool = distance < 0.01
    if is_circular:
        logger.info("Trail detected as circular (endpoints %.4f deg apart)", distance)
    return is_circular


def _build_hike(
    raw_steps: list[tuple[Station, Station, LineString, float]],
    matched_stations: list[MatchedStation],
    path_ref: str,
    path_name: str,
    osm_relation_id: int,
    route_type: str,
    is_circular: bool,
    is_round_trip: bool,
    srtm_reader: SrtmReader,
) -> Hike:
    """Build a Hike object from raw steps, computing elevation and exporting files."""
    enriched_steps, _connectors_cached = attach_connectors(
        raw_steps, matched_stations, CONNECTOR_SKIP_THRESHOLD_METERS
    )

    first_start_station = enriched_steps[0][0]
    last_end_station = enriched_steps[-1][1]

    steps: list[HikeStep] = []
    geometries: list[LineString] = []
    step_profiles = []
    all_segment_elevations: list[list[float | None]] = []
    total_distance_km = 0.0
    total_gain = 0
    total_loss = 0
    overall_max_elevation = 0
    overall_min_elevation = 99999

    for start_station, end_station, geometry, distance_km in enriched_steps:
        profile = compute_elevation_profile(geometry, srtm_reader, ELEVATION_SAMPLE_INTERVAL_METERS)
        step_profiles.append(profile)

        vertex_elevations = elevations_for_geometry(geometry, srtm_reader)
        all_segment_elevations.append(vertex_elevations)

        estimated_step_duration = (
            profile.duration_minutes
            if profile.duration_minutes > 0
            else estimate_duration(distance_km, profile.gain_m)
        )

        steps.append(
            HikeStep(
                start_station=start_station,
                end_station=end_station,
                distance_km=distance_km,
                estimated_duration_minutes=estimated_step_duration,
                elevation_gain_meters=profile.gain_m,
                elevation_loss_meters=profile.loss_m,
            )
        )
        geometries.append(geometry)
        total_distance_km += distance_km
        total_gain += profile.gain_m
        total_loss += profile.loss_m
        if profile.max_m > 0:
            overall_max_elevation = max(overall_max_elevation, profile.max_m)
        if profile.min_m > 0:
            overall_min_elevation = min(overall_min_elevation, profile.min_m)

    total_distance_km = round(total_distance_km, 1)
    total_duration_minutes = sum(step.estimated_duration_minutes for step in steps)

    if overall_min_elevation == 99999:
        overall_min_elevation = 0

    difficulty = classify_difficulty(total_gain, total_loss, total_distance_km)

    if is_round_trip:
        hike_slug = slugify(f"{path_ref} {first_start_station.name} loop")
        loop_end_key = f"{first_start_station.name}-loop"
        hike_id = generate_hike_id(path_ref, first_start_station.name, loop_end_key)
        hike_name = f"{path_ref}: {first_start_station.name} loop"
    else:
        hike_slug = slugify(f"{path_ref} {first_start_station.name} to {last_end_station.name}")
        hike_id = generate_hike_id(path_ref, first_start_station.name, last_end_station.name)
        hike_name = f"{path_ref}: {first_start_station.name} to {last_end_station.name}"

    gpx_path = f"gpx/{hike_id}.gpx"
    geojson_path = f"geojson/{hike_id}.json"

    combined_bounds = _compute_combined_bounds(geometries)

    export_gpx(
        segments=geometries,
        name=hike_name,
        description=f"Hiking on {path_ref} ({len(steps)} step{'s' if len(steps) > 1 else ''})",
        output_path=str(Path(OUTPUT_DIRECTORY).expanduser() / gpx_path),
        segment_elevations=all_segment_elevations,
    )

    export_geojson(
        segments=geometries,
        hike_id=hike_id,
        name=hike_name,
        output_path=str(Path(OUTPUT_DIRECTORY).expanduser() / geojson_path),
    )

    export_elevation_profile(
        step_profiles=step_profiles,
        hike_id=hike_id,
        output_directory=str(Path(ELEVATION_DIRECTORY).expanduser()),
    )

    step_summary = (
        " → ".join(f"{step.start_station.name}" for step in steps)
        + f" → {steps[-1].end_station.name}"
    )
    logger.info(
        "  %s (%d steps, %.1f km, ~%dmin, D+%dm)",
        step_summary,
        len(steps),
        total_distance_km,
        total_duration_minutes,
        total_gain,
    )

    return Hike(
        identifier=hike_id,
        slug=hike_slug,
        path_ref=path_ref,
        path_name=path_name,
        osm_relation_id=osm_relation_id,
        start_station=first_start_station,
        end_station=last_end_station,
        steps=steps,
        distance_km=total_distance_km,
        estimated_duration_minutes=total_duration_minutes,
        elevation_gain_meters=total_gain,
        elevation_loss_meters=total_loss,
        max_elevation_meters=overall_max_elevation,
        min_elevation_meters=overall_min_elevation,
        difficulty=difficulty,
        bounding_box=combined_bounds,
        region="",
        departement="",
        gpx_path=gpx_path,
        geojson_path=geojson_path,
        is_reversible=True,
        last_updated=date.today().isoformat(),
        route_type=route_type,
        is_circular_trail=is_circular,
        is_round_trip=is_round_trip,
    )


def _compute_combined_bounds(
    geometries: list[LineString],
) -> tuple[float, float, float, float]:
    """Compute the bounding box encompassing all geometries."""
    combined = unary_union(geometries)
    bounds = combined.bounds
    return (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
