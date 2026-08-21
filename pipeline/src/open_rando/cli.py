from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, MultiLineString

from open_rando.commands.images import add_images_subparser
from open_rando.commands.osm_index import add_osm_index_subparser
from open_rando.config import (
    CATALOG_PATH,
    ELEVATION_DIRECTORY,
    ELEVATION_SAMPLE_INTERVAL_METERS,
    GEOJSON_DIRECTORY,
    GPX_DIRECTORY,
    MAX_BUS_STOP_DISTANCE_METERS,
    MAX_STATION_DISTANCE_METERS,
    MIN_TRAIN_STATIONS_PER_ROUTE,
    OUTPUT_DIRECTORY,
    OVERPASS_COOLDOWN_SECONDS,
    RUN_REPORT_PATH,
    SRTM_BASE_URL,
    SRTM_CACHE_DIRECTORY,
    TRAIN_GTFS_MATCH_RADIUS_METERS,
)
from open_rando.exporters.catalog import export_route_catalog
from open_rando.exporters.elevation import export_route_elevation
from open_rando.exporters.geojson import export_route_geojson
from open_rando.exporters.gpx import export_route_gpx
from open_rando.exporters.image_generator import find_image_on_disk
from open_rando.exporters.report import build_run_report, export_run_report, log_run_report
from open_rando.fetchers.discovery import discover_routes
from open_rando.fetchers.gtfs import (
    GtfsStop,
    annotate_station_connectivity,
    build_rail_service,
    fetch_gtfs_feed_data,
    fetch_gtfs_stops,
    fetch_resource_url_map,
    filter_and_annotate_bus_stops,
    match_stations_to_gtfs_stops,
    resolve_transit_line_names,
)
from open_rando.fetchers.landmarks import fetch_landmarks
from open_rando.fetchers.overpass import chain_linestrings, fetch_trail
from open_rando.fetchers.pois import (
    POI_ACCOMMODATION_RADIUS_METERS,
    fetch_accommodation_pois,
    filter_pois_by_trail_distance,
)
from open_rando.fetchers.sncf import build_sncf_code_set, fetch_sncf_stations
from open_rando.fetchers.srtm import SrtmReader
from open_rando.fetchers.stations import fetch_stations, filter_stations_by_sncf
from open_rando.models import PointOfInterest, Route, generate_route_id, slugify, slugify_sncf
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
    resolve_departement,
    resolve_region,
)
from open_rando.processors.match import (
    match_stations_to_trail,
    refine_junctions_by_walking_distance,
)
from open_rando.processors.slice import (
    compute_segments_distance_km,
    compute_trail_gaps_km,
    extract_substring_segments,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("open_rando")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="open-rando — GR route catalog + image generation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Build/refresh the route catalog from OSM + SNCF + GTFS sources.",
    )
    pipeline_parser.add_argument(
        "--route",
        type=str,
        help="Process a single route by ref (e.g. 'GR 13').",
    )
    pipeline_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List discovered routes without processing them.",
    )
    pipeline_parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear the catalog before processing. "
        "Without this flag, existing routes are preserved.",
    )
    pipeline_parser.set_defaults(func=run_pipeline)

    add_images_subparser(subparsers)
    add_osm_index_subparser(subparsers)

    arguments = parser.parse_args()
    arguments.func(arguments)


def run_pipeline(arguments: argparse.Namespace) -> None:
    discovered = discover_routes()

    if arguments.route:
        discovered = [route for route in discovered if route["ref"] == arguments.route]
        if not discovered:
            logger.error("Route '%s' not found in discovered routes", arguments.route)
            return

    if arguments.dry_run:
        logger.info("Discovered %d routes:", len(discovered))
        for route in discovered:
            logger.info(
                "  %s — %s (relation %d)",
                route["ref"],
                route["name"],
                route["relation_id"],
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
    sncf_insee = build_sncf_insee_index(sncf_records)
    if sncf_codes:
        logger.info("Loaded %d SNCF station codes for filtering", len(sncf_codes))

    all_routes: list[Route] = []
    successful_routes = 0
    failed_routes: list[str] = []
    skipped_routes: list[str] = []
    catalog_path = str(Path(CATALOG_PATH).expanduser())

    # Load existing catalog for merging (default), or start fresh with --reset
    existing_route_dicts: list[dict[str, Any]] = []
    if not arguments.reset and Path(catalog_path).exists():
        with open(catalog_path, encoding="utf-8") as catalog_file:
            existing_catalog = json.load(catalog_file)
        existing_route_dicts = existing_catalog.get("routes", [])
        logger.info(
            "Loaded %d existing routes from catalog",
            len(existing_route_dicts),
        )
    elif arguments.reset:
        logger.info("Catalog reset — starting fresh")

    # Images are named after the route id, which is derived from ref + relation
    # id, so they can be recovered from disk. Reading the previous catalog alone
    # would orphan every generated image on a --reset run.
    existing_image_paths: dict[int, str] = {
        int(entry["osm_relation_id"]): str(entry["image_path"])
        for entry in existing_route_dicts
        if entry.get("image_path")
    }

    previous_route_used_api = False

    for route_index, discovered_route in enumerate(discovered):
        route_ref = str(discovered_route["ref"])
        fallback_ids = [discovered_route["relation_id"]]
        route_relation_ids: list[int] = [
            int(relation_id) for relation_id in discovered_route.get("relation_ids", fallback_ids)
        ]
        if route_index > 0 and previous_route_used_api:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)

        relation_label = ", ".join(str(relation_id) for relation_id in route_relation_ids)
        logger.info(
            "=== [%d/%d] Processing %s (relations: %s) ===",
            route_index + 1,
            len(discovered),
            route_ref,
            relation_label,
        )

        try:
            route_description = str(discovered_route.get("description", ""))
            route_name = str(discovered_route.get("name", ""))
            processed_route, all_cached = _process_route(
                relation_ids=route_relation_ids,
                route_ref=route_ref,
                route_name=route_name,
                route_description=route_description,
                srtm_reader=srtm_reader,
                sncf_codes=sncf_codes,
                sncf_insee=sncf_insee,
            )
            if processed_route is not None:
                processed_route.image_path = existing_image_paths.get(
                    processed_route.osm_relation_id
                ) or find_image_on_disk(processed_route.identifier)
                all_routes.append(processed_route)
                poi_counts: dict[str, int] = {}
                for poi in processed_route.pois:
                    poi_counts[poi.poi_type] = poi_counts.get(poi.poi_type, 0) + 1
                counts_str = ", ".join(
                    f"{count} {poi_type}" for poi_type, count in sorted(poi_counts.items())
                )
                logger.info("  -> %s: %s", processed_route.path_ref, counts_str)
            else:
                skipped_routes.append(route_ref)
            successful_routes += 1
            previous_route_used_api = not all_cached
        except Exception:
            logger.exception("Failed to process %s, skipping", route_ref)
            failed_routes.append(route_ref)
            previous_route_used_api = True

    # Merge: replace updated routes in existing catalog, keep the rest
    processed_relation_ids = {route.osm_relation_id for route in all_routes}
    merged_dicts: list[Route | dict[str, Any]] = [
        route_dict
        for route_dict in existing_route_dicts
        if int(route_dict["osm_relation_id"]) not in processed_relation_ids
    ]
    merged_dicts.extend(all_routes)
    merged_dicts.sort(
        key=lambda entry: str(
            entry.path_ref if isinstance(entry, Route) else entry.get("path_ref", "")
        )
    )
    current_route_dicts: list[dict[str, Any]] = [
        entry.to_dict() if isinstance(entry, Route) else entry for entry in merged_dicts
    ]
    export_route_catalog(current_route_dicts, catalog_path)

    report_path = str(Path(RUN_REPORT_PATH).expanduser())
    report = build_run_report(
        previous_routes=existing_route_dicts,
        current_routes=current_route_dicts,
        failed_route_refs=failed_routes,
        skipped_route_refs=skipped_routes,
    )
    export_run_report(report, report_path)

    logger.info("=== Summary ===")
    logger.info("Routes processed: %d/%d", successful_routes, len(discovered))
    logger.info("Total routes in catalog: %d", len(merged_dicts))
    logger.info("Catalog written to %s", catalog_path)
    log_run_report(report)
    logger.info("Run report written to %s", report_path)


def _fetch_and_fuse_trails(
    relation_ids: list[int],
) -> tuple[LineString | MultiLineString, dict[str, str | int], bool]:
    """Fetch trails from multiple OSM relations and fuse into one geometry."""
    all_linestrings: list[LineString] = []
    primary_metadata: dict[str, str | int] = {}
    all_cached = True

    for index, relation_id in enumerate(relation_ids):
        if index > 0:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)

        trail, metadata, cached = fetch_trail(relation_id)
        all_cached = all_cached and cached

        if index == 0:
            primary_metadata = metadata

        if isinstance(trail, MultiLineString):
            all_linestrings.extend(trail.geoms)
        else:
            all_linestrings.append(trail)

    if len(all_linestrings) == 1:
        combined = all_linestrings[0]
    else:
        combined = chain_linestrings(all_linestrings)

    primary_metadata["osm_relation_id"] = relation_ids[0]
    return combined, primary_metadata, all_cached


def _process_route(
    relation_ids: list[int],
    route_ref: str,
    route_name: str,
    route_description: str,
    srtm_reader: SrtmReader,
    sncf_codes: set[str],
    sncf_insee: dict[str, str],
) -> tuple[Route | None, bool]:
    """Process a route and return a Route with POIs for map display."""
    # Fetch and fuse trails from all relation_ids
    trail, trail_metadata, trail_cached = _fetch_and_fuse_trails(relation_ids)

    if not trail_cached:
        time.sleep(OVERPASS_COOLDOWN_SECONDS)

    # Fetch all stations (train + bus) near the trail
    stations, stations_cached = fetch_stations(trail)
    all_cached = trail_cached and stations_cached

    # Train station POIs (SNCF-filtered)
    sncf_stations = filter_stations_by_sncf(stations, sncf_codes) if sncf_codes else stations

    train_stations = [station for station in sncf_stations if station.transport_type == "train"]
    matched_trains = match_stations_to_trail(
        train_stations,
        trail,
        MAX_STATION_DISTANCE_METERS,
    )
    matched_trains = refine_junctions_by_walking_distance(matched_trains, trail)

    if len(matched_trains) < MIN_TRAIN_STATIONS_PER_ROUTE:
        logger.warning(
            "Only %d train stations (need %d), skipping route",
            len(matched_trains),
            MIN_TRAIN_STATIONS_PER_ROUTE,
        )
        return None, all_cached

    train_pois = [
        PointOfInterest(
            name=station.name,
            lat=station.lat,
            lon=station.lon,
            poi_type="train_station",
            url=_build_sncf_url(station.name),
        )
        for station, _fraction, _junction in matched_trains
    ]

    # Bus stop POIs — enrich with GTFS route names
    bus_stops = [station for station in stations if station.transport_type == "bus"]
    matched_buses = match_stations_to_trail(
        bus_stops,
        trail,
        MAX_BUS_STOP_DISTANCE_METERS,
    )

    # GTFS enrichment: bus stops get route names, train stations get departures
    route_names: dict[str, str] = {}
    matched_train_stations = [station for station, _fraction, _junction in matched_trains]
    matched_bus_stations = [station for station, _fraction, _junction in matched_buses]

    gtfs_bounds = trail.bounds
    gtfs_stops, gtfs_cached = fetch_gtfs_stops(
        south=gtfs_bounds[1] - 0.05,
        west=gtfs_bounds[0] - 0.05,
        north=gtfs_bounds[3] + 0.05,
        east=gtfs_bounds[2] + 0.05,
    )
    all_cached = all_cached and gtfs_cached

    bus_gtfs_stop_map: dict[str, list[GtfsStop]] = {}
    if matched_bus_stations:
        _, bus_gtfs_stop_map = filter_and_annotate_bus_stops(matched_bus_stations, gtfs_stops)

    train_gtfs_stop_map = match_stations_to_gtfs_stops(
        matched_train_stations,
        gtfs_stops,
        TRAIN_GTFS_MATCH_RADIUS_METERS,
    )

    resource_ids = {
        gtfs_stop.resource_id
        for matches in (*bus_gtfs_stop_map.values(), *train_gtfs_stop_map.values())
        for gtfs_stop in matches
    }
    if resource_ids:
        resource_url_map = fetch_resource_url_map()
        feed_data = fetch_gtfs_feed_data(resource_ids, resource_url_map)
        route_names = feed_data.route_names

        if matched_bus_stations:
            annotate_station_connectivity(
                matched_bus_stations,
                bus_gtfs_stop_map,
                feed_data.connectivity,
            )

        for station in matched_train_stations:
            station.rail_service = build_rail_service(
                train_gtfs_stop_map.get(station.code, []),
                feed_data.departures,
            )

        stations_with_service = sum(
            1 for station in matched_train_stations if station.rail_service is not None
        )
        logger.info(
            "  Rail service: %d/%d train stations with GTFS departures",
            stations_with_service,
            len(matched_train_stations),
        )

    for poi, station in zip(train_pois, matched_train_stations, strict=True):
        poi.rail_service = station.rail_service

    bus_pois = []
    for station, _fraction, _junction in matched_buses:
        if station.connected_route_ids:
            lines = resolve_transit_line_names(station.connected_route_ids, route_names)
        else:
            lines = station.transit_lines
        bus_pois.append(
            PointOfInterest(
                name=station.name,
                lat=station.lat,
                lon=station.lon,
                poi_type="bus_stop",
                transit_lines=lines,
            )
        )

    # Accommodation POIs (hotels + campings within 3km)
    if not stations_cached:
        time.sleep(OVERPASS_COOLDOWN_SECONDS)

    accommodation_pois, accommodation_cached = fetch_accommodation_pois(trail)
    accommodation_pois = filter_pois_by_trail_distance(
        accommodation_pois,
        trail,
        POI_ACCOMMODATION_RADIUS_METERS,
    )
    all_cached = all_cached and accommodation_cached

    if not accommodation_cached:
        time.sleep(OVERPASS_COOLDOWN_SECONDS)

    landmarks, landmarks_cached = fetch_landmarks(trail)
    all_cached = all_cached and landmarks_cached

    all_pois = train_pois + bus_pois + accommodation_pois

    # Trail metadata
    path_ref = route_ref or str(trail_metadata["ref"])
    path_name = route_name or str(trail_metadata["name"])
    osm_relation_id = int(trail_metadata["osm_relation_id"])

    route_id = generate_route_id(path_ref, osm_relation_id)
    route_slug = slugify(path_ref)

    # Elevation profile for the full trail, segment by segment so the gaps
    # between mapped segments are never charged as distance, climb or time.
    profile = compute_trail_elevation_profile(
        trail,
        srtm_reader,
        ELEVATION_SAMPLE_INTERVAL_METERS,
    )

    # GPX carries an elevation per vertex, in trail order — no distance involved.
    if isinstance(trail, MultiLineString):
        all_coords: list[tuple[float, ...]] = []
        for segment in trail.geoms:
            all_coords.extend(segment.coords)
        vertex_line = LineString(all_coords)
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

    # Annotate train station POIs with haversine distance along the trail.
    # We cannot use fraction * total_distance_km because the fraction comes from
    # Shapely's Euclidean project() in degree-space, while the elevation profile
    # uses haversine distances. Extract the actual trail substring and measure it.
    for poi, (_station, fraction, _junction) in zip(train_pois, matched_trains, strict=True):
        pieces_to_station = extract_substring_segments(trail, 0.0, fraction)
        poi.distance_km = round(compute_segments_distance_km(pieces_to_station), 2)

    # Geography
    trail_bounds = trail.bounds
    forest_polygons = fetch_forest_areas(trail_bounds)
    is_circular = _detect_circular_trail(trail)

    matched_station_codes = [station.code for station, _fraction, _junction in matched_trains]
    departement = resolve_departement(matched_station_codes[0], sncf_insee)
    region = resolve_region(departement)
    forest_ratio = compute_forest_ratio(trail, forest_polygons)
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

    bounding_box = (
        float(trail_bounds[0]),
        float(trail_bounds[1]),
        float(trail_bounds[2]),
        float(trail_bounds[3]),
    )

    # Export files
    gpx_path = f"gpx/{route_id}.gpx"
    geojson_path = f"geojson/{route_id}.json"

    export_route_gpx(
        trail=trail,
        name=path_ref,
        description=f"{path_name}",
        pois=all_pois,
        output_path=str(Path(OUTPUT_DIRECTORY).expanduser() / gpx_path),
        elevations=vertex_elevations,
    )

    export_route_geojson(
        trail=trail,
        route_id=route_id,
        name=path_ref,
        pois=all_pois,
        output_path=str(Path(OUTPUT_DIRECTORY).expanduser() / geojson_path),
    )

    export_route_elevation(
        profile=profile,
        route_id=route_id,
        output_directory=str(Path(ELEVATION_DIRECTORY).expanduser()),
        station_positions_km=[poi.distance_km for poi in train_pois if poi.distance_km is not None],
    )

    logger.info(
        "  POIs: %d train, %d bus, %d accommodation",
        len(train_pois),
        len(bus_pois),
        len(accommodation_pois),
    )

    route = Route(
        identifier=route_id,
        slug=route_slug,
        path_ref=path_ref,
        path_name=path_name,
        description=route_description,
        osm_relation_id=osm_relation_id,
        pois=all_pois,
        distance_km=total_distance_km,
        elevation_gain_meters=profile.gain_m,
        elevation_loss_meters=profile.loss_m,
        max_elevation_meters=profile.max_m,
        min_elevation_meters=profile.min_m,
        bounding_box=bounding_box,
        region=region,
        departement=departement,
        difficulty=difficulty,
        is_circular_trail=is_circular,
        terrain=terrain,
        trail_segment_count=trail_segment_count,
        trail_gap_km=trail_gap_km,
        geojson_path=geojson_path,
        gpx_path=gpx_path,
        last_updated=date.today().isoformat(),
        landmarks=landmarks,
    )

    return route, all_cached


def _build_sncf_url(station_name: str) -> str:
    """Build a garesetconnexions.sncf URL from a station name."""
    slug = slugify_sncf(station_name)
    return f"https://www.garesetconnexions.sncf/fr/gares-services/{slug}/horaires"


def _detect_circular_trail(trail: LineString | MultiLineString) -> bool:
    """Detect if a trail is circular (first and last points within threshold)."""
    if isinstance(trail, MultiLineString):
        first_point = trail.geoms[0].coords[0]
        last_point = trail.geoms[-1].coords[-1]
    else:
        first_point = trail.coords[0]
        last_point = trail.coords[-1]

    distance_degrees = float(
        ((first_point[0] - last_point[0]) ** 2 + (first_point[1] - last_point[1]) ** 2) ** 0.5
    )
    # ~5km threshold
    return distance_degrees < 0.05
