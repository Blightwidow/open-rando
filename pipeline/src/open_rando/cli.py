from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from open_rando.config import (
    CATALOG_PATH,
    GEOJSON_DIRECTORY,
    GPX_DIRECTORY,
    GR13_RELATION_ID,
    MAX_STATION_DISTANCE_METERS,
    OUTPUT_DIRECTORY,
    WALKING_SPEED_KMH,
)
from open_rando.exporters.catalog import export_catalog
from open_rando.exporters.geojson import export_geojson
from open_rando.exporters.gpx import export_gpx
from open_rando.fetchers.overpass import fetch_trail
from open_rando.fetchers.stations import fetch_stations
from open_rando.models import Hike, generate_hike_id, slugify
from open_rando.processors.match import match_stations_to_trail
from open_rando.processors.slice import compute_segment_distance_km, slice_segments

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("open_rando")


def main() -> None:
    logger.info("Fetching GR 13 trail from Overpass API...")
    trail, trail_metadata = fetch_trail(GR13_RELATION_ID)

    logger.info("Fetching stations near trail...")
    stations = fetch_stations(trail)

    logger.info("Matching stations to trail...")
    matched = match_stations_to_trail(stations, trail, MAX_STATION_DISTANCE_METERS)

    logger.info("Slicing segments...")
    segments = slice_segments(trail, matched)
    logger.info("Created %d segments", len(segments))

    Path(GPX_DIRECTORY).mkdir(parents=True, exist_ok=True)
    Path(GEOJSON_DIRECTORY).mkdir(parents=True, exist_ok=True)

    path_ref = str(trail_metadata["ref"])
    path_name = str(trail_metadata["name"])
    osm_relation_id = int(trail_metadata["osm_relation_id"])

    hikes: list[Hike] = []
    for start_station, end_station, segment in segments:
        distance_km = round(compute_segment_distance_km(segment), 1)
        estimated_duration_minutes = int(distance_km / WALKING_SPEED_KMH * 60)

        hike_slug = slugify(f"{path_ref} {start_station.name} to {end_station.name}")
        hike_id = generate_hike_id(path_ref, start_station.name, end_station.name)

        gpx_path = f"gpx/{hike_id}.gpx"
        geojson_path = f"geojson/{hike_id}.json"

        hike = Hike(
            identifier=hike_id,
            slug=hike_slug,
            path_ref=path_ref,
            path_name=path_name,
            osm_relation_id=osm_relation_id,
            start_station=start_station,
            end_station=end_station,
            distance_km=distance_km,
            estimated_duration_minutes=estimated_duration_minutes,
            elevation_gain_meters=0,
            elevation_loss_meters=0,
            max_elevation_meters=0,
            min_elevation_meters=0,
            difficulty="unknown",
            bounding_box=segment.bounds,
            region="",
            departement="",
            gpx_path=gpx_path,
            geojson_path=geojson_path,
            is_reversible=True,
            last_updated=date.today().isoformat(),
        )
        hikes.append(hike)

        segment_name = f"{path_ref}: {start_station.name} to {end_station.name}"

        export_gpx(
            segment=segment,
            name=segment_name,
            description=f"Hiking segment on {path_ref}",
            output_path=str(Path(OUTPUT_DIRECTORY) / gpx_path),
        )

        export_geojson(
            segment=segment,
            hike_id=hike_id,
            name=segment_name,
            output_path=str(Path(OUTPUT_DIRECTORY) / geojson_path),
        )

        logger.info("  %s (%.1f km, ~%dmin)", segment_name, distance_km, estimated_duration_minutes)

    export_catalog(hikes, CATALOG_PATH)
    logger.info("Catalog written to %s with %d hikes", CATALOG_PATH, len(hikes))
