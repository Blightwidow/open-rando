from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

from shapely.geometry import LineString
from shapely.ops import unary_union

from open_rando.config import (
    CATALOG_PATH,
    ELEVATION_DIRECTORY,
    ELEVATION_SAMPLE_INTERVAL_METERS,
    GEOJSON_DIRECTORY,
    GPX_DIRECTORY,
    GR13_RELATION_ID,
    MAX_STATION_DISTANCE_METERS,
    MAX_STEP_DISTANCE_KM,
    MIN_STEP_DISTANCE_KM,
    OUTPUT_DIRECTORY,
    SRTM_BASE_URL,
    SRTM_CACHE_DIRECTORY,
)
from open_rando.exporters.catalog import export_catalog
from open_rando.exporters.elevation import export_elevation_profile
from open_rando.exporters.geojson import export_geojson
from open_rando.exporters.gpx import export_gpx
from open_rando.fetchers.accommodation import fetch_accommodation
from open_rando.fetchers.overpass import fetch_trail
from open_rando.fetchers.srtm import SrtmReader
from open_rando.fetchers.stations import fetch_stations
from open_rando.models import Hike, HikeStep, generate_hike_id, slugify
from open_rando.processors.elevation import (
    classify_difficulty,
    compute_elevation_profile,
    elevations_for_geometry,
    estimate_duration,
)
from open_rando.processors.match import match_stations_to_trail
from open_rando.processors.slice import find_hikes

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("open_rando")


def main() -> None:
    overpass_cooldown_seconds = 5

    logger.info("Fetching GR 13 trail from Overpass API...")
    trail, trail_metadata = fetch_trail(GR13_RELATION_ID)

    time.sleep(overpass_cooldown_seconds)

    logger.info("Fetching stations near trail...")
    stations = fetch_stations(trail)

    logger.info("Matching stations to trail...")
    matched = match_stations_to_trail(stations, trail, MAX_STATION_DISTANCE_METERS)

    time.sleep(overpass_cooldown_seconds)

    matched_stations = [station for station, _fraction in matched]
    logger.info("Fetching accommodation near %d matched stations...", len(matched_stations))
    fetch_accommodation(matched_stations)

    logger.info(
        "Finding multi-step hikes (step range: %s-%s km)...",
        MIN_STEP_DISTANCE_KM,
        MAX_STEP_DISTANCE_KM,
    )
    raw_hikes = find_hikes(trail, matched, MIN_STEP_DISTANCE_KM, MAX_STEP_DISTANCE_KM)
    logger.info("Found %d hikes", len(raw_hikes))

    Path(GPX_DIRECTORY).mkdir(parents=True, exist_ok=True)
    Path(GEOJSON_DIRECTORY).mkdir(parents=True, exist_ok=True)
    Path(ELEVATION_DIRECTORY).mkdir(parents=True, exist_ok=True)

    srtm_reader = SrtmReader(
        cache_directory=str(Path(SRTM_CACHE_DIRECTORY).expanduser()),
        base_url=SRTM_BASE_URL,
    )

    path_ref = str(trail_metadata["ref"])
    path_name = str(trail_metadata["name"])
    osm_relation_id = int(trail_metadata["osm_relation_id"])

    hikes: list[Hike] = []
    for raw_steps in raw_hikes:
        first_start_station = raw_steps[0][0]
        last_end_station = raw_steps[-1][1]

        steps: list[HikeStep] = []
        geometries: list[LineString] = []
        step_profiles = []
        all_segment_elevations: list[list[float | None]] = []
        total_distance_km = 0.0
        total_gain = 0
        total_loss = 0
        overall_max_elevation = 0
        overall_min_elevation = 99999

        for start_station, end_station, geometry, distance_km in raw_steps:
            profile = compute_elevation_profile(
                geometry, srtm_reader, ELEVATION_SAMPLE_INTERVAL_METERS
            )
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

        hike_slug = slugify(f"{path_ref} {first_start_station.name} to {last_end_station.name}")
        hike_id = generate_hike_id(path_ref, first_start_station.name, last_end_station.name)

        gpx_path = f"gpx/{hike_id}.gpx"
        geojson_path = f"geojson/{hike_id}.json"

        combined_bounds = _compute_combined_bounds(geometries)

        hike = Hike(
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
        )
        hikes.append(hike)

        hike_name = f"{path_ref}: {first_start_station.name} to {last_end_station.name}"

        export_gpx(
            segments=geometries,
            name=hike_name,
            description=f"Hiking on {path_ref} ({len(steps)} step{'s' if len(steps) > 1 else ''})",
            output_path=str(Path(OUTPUT_DIRECTORY) / gpx_path),
            segment_elevations=all_segment_elevations,
        )

        export_geojson(
            segments=geometries,
            hike_id=hike_id,
            name=hike_name,
            output_path=str(Path(OUTPUT_DIRECTORY) / geojson_path),
        )

        export_elevation_profile(
            step_profiles=step_profiles,
            hike_id=hike_id,
            output_directory=ELEVATION_DIRECTORY,
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

    export_catalog(hikes, CATALOG_PATH)
    logger.info("Catalog written to %s with %d hikes", CATALOG_PATH, len(hikes))


def _compute_combined_bounds(
    geometries: list[LineString],
) -> tuple[float, float, float, float]:
    """Compute the bounding box encompassing all geometries."""
    combined = unary_union(geometries)
    bounds = combined.bounds
    return (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
