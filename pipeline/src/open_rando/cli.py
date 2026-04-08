from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

from shapely.geometry import LineString
from shapely.ops import unary_union

from open_rando.config import (
    CATALOG_PATH,
    GEOJSON_DIRECTORY,
    GPX_DIRECTORY,
    GR13_RELATION_ID,
    MAX_STATION_DISTANCE_METERS,
    MAX_STEP_DISTANCE_KM,
    MIN_STEP_DISTANCE_KM,
    OUTPUT_DIRECTORY,
    WALKING_SPEED_KMH,
)
from open_rando.exporters.catalog import export_catalog
from open_rando.exporters.geojson import export_geojson
from open_rando.exporters.gpx import export_gpx
from open_rando.fetchers.accommodation import fetch_accommodation
from open_rando.fetchers.overpass import fetch_trail
from open_rando.fetchers.stations import fetch_stations
from open_rando.models import Hike, HikeStep, generate_hike_id, slugify
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

    path_ref = str(trail_metadata["ref"])
    path_name = str(trail_metadata["name"])
    osm_relation_id = int(trail_metadata["osm_relation_id"])

    hikes: list[Hike] = []
    for raw_steps in raw_hikes:
        first_start_station = raw_steps[0][0]
        last_end_station = raw_steps[-1][1]

        steps: list[HikeStep] = []
        geometries: list[LineString] = []
        total_distance_km = 0.0

        for start_station, end_station, geometry, distance_km in raw_steps:
            estimated_step_duration = int(distance_km / WALKING_SPEED_KMH * 60)
            steps.append(
                HikeStep(
                    start_station=start_station,
                    end_station=end_station,
                    distance_km=distance_km,
                    estimated_duration_minutes=estimated_step_duration,
                )
            )
            geometries.append(geometry)
            total_distance_km += distance_km

        total_distance_km = round(total_distance_km, 1)
        total_duration_minutes = int(total_distance_km / WALKING_SPEED_KMH * 60)

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
            elevation_gain_meters=0,
            elevation_loss_meters=0,
            max_elevation_meters=0,
            min_elevation_meters=0,
            difficulty="unknown",
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
        )

        export_geojson(
            segments=geometries,
            hike_id=hike_id,
            name=hike_name,
            output_path=str(Path(OUTPUT_DIRECTORY) / geojson_path),
        )

        step_summary = (
            " → ".join(f"{step.start_station.name}" for step in steps)
            + f" → {steps[-1].end_station.name}"
        )
        logger.info(
            "  %s (%d steps, %.1f km, ~%dmin)",
            step_summary,
            len(steps),
            total_distance_km,
            total_duration_minutes,
        )

    export_catalog(hikes, CATALOG_PATH)
    logger.info("Catalog written to %s with %d hikes", CATALOG_PATH, len(hikes))


def _compute_combined_bounds(
    geometries: list[LineString],
) -> tuple[float, float, float, float]:
    """Compute the bounding box encompassing all geometries."""
    combined = unary_union(geometries)
    return combined.bounds
