"""`images` subcommand — generate hero illustrations from the route catalog.

Reads `catalog.json`, rebuilds the minimal `Route` shape needed by
`build_image_prompt`, and delegates to `generate_image`. Writes the resulting
`image_path` back into the catalog so the website picks it up.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from open_rando.config import CATALOG_PATH, OUTPUT_DIRECTORY
from open_rando.exporters.image_generator import (
    IMAGES_SUBDIRECTORY,
    build_image_content,
    generate_image,
)
from open_rando.exporters.image_generator import (
    _read_stored_prompt as read_stored_prompt,
)
from open_rando.exporters.image_generator import (
    _write_stored_prompt as write_stored_prompt,
)
from open_rando.models import Landmark, PointOfInterest, Route

logger = logging.getLogger("open_rando")


def add_images_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "images",
        help="Generate AI hero illustrations for routes already in the catalog.",
    )
    parser.add_argument(
        "--route",
        type=str,
        help="Generate the image for a single route by ref (e.g. 'GR 13').",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Force regeneration even when the prompt is unchanged.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report cache hit/miss/forced per route without loading the model.",
    )
    parser.add_argument(
        "--populate-prompts",
        action="store_true",
        help=(
            "Write freshly-built image_prompt content for every catalog route into "
            "routes.yaml. Overwrites existing entries. Skips image generation."
        ),
    )
    parser.set_defaults(func=run_images)


def run_images(arguments: argparse.Namespace) -> None:
    catalog_path = Path(CATALOG_PATH).expanduser()
    if not catalog_path.exists():
        logger.error("Catalog not found at %s — run `pipeline` first.", catalog_path)
        return

    with catalog_path.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)

    route_dicts: list[dict[str, Any]] = catalog.get("routes", [])

    if arguments.route:
        targets = [entry for entry in route_dicts if entry.get("path_ref") == arguments.route]
        if not targets:
            logger.error("Route '%s' not found in catalog", arguments.route)
            return
    else:
        targets = list(route_dicts)

    output_directory = Path(OUTPUT_DIRECTORY).expanduser()

    if arguments.populate_prompts:
        _populate_prompts(targets)
        return

    if arguments.dry_run:
        _report_cache_status(targets, output_directory)
        return

    updates: dict[str, str | None] = {}
    for route_dict in targets:
        route = _route_from_catalog_entry(route_dict)
        relative_path = f"{IMAGES_SUBDIRECTORY}/{route.identifier}.webp"
        output_path = output_directory / relative_path

        if read_stored_prompt(route.path_ref) is None:
            if output_path.exists():
                output_path.unlink()
                logger.info(
                    "  Removed %s for %s — image_prompt absent in routes.yaml",
                    relative_path,
                    route.path_ref,
                )
            if route_dict.get("image_path"):
                updates[route.identifier] = None
            continue

        image_path = generate_image(route, output_directory, force=arguments.regenerate)
        if image_path is not None:
            updates[route.identifier] = image_path

    if not updates:
        logger.info("No image_path updates to write.")
        return

    for entry in route_dicts:
        identifier = str(entry.get("id"))
        if identifier not in updates:
            continue
        new_path = updates[identifier]
        if new_path is None:
            entry.pop("image_path", None)
        else:
            entry["image_path"] = new_path

    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Updated %d image_path entries in %s", len(updates), catalog_path)


def _report_cache_status(targets: list[dict[str, Any]], output_directory: Path) -> None:
    for route_dict in targets:
        route = _route_from_catalog_entry(route_dict)
        stored_content = read_stored_prompt(route.path_ref)
        relative_path = f"{IMAGES_SUBDIRECTORY}/{route.identifier}.webp"
        file_exists = (output_directory / relative_path).exists()

        if stored_content is None:
            logger.info("  %-12s skip (no image_prompt)", route.path_ref)
            continue

        status = "hit" if file_exists else "miss (file missing)"
        logger.info("  %-12s %s — %s", route.path_ref, status, relative_path)
        logger.info("    content: %s", stored_content)


def _populate_prompts(targets: list[dict[str, Any]]) -> None:
    written = 0
    for route_dict in targets:
        route = _route_from_catalog_entry(route_dict)
        content = build_image_content(route)
        write_stored_prompt(route.path_ref, content)
        written += 1
    logger.info("Wrote image_prompt content for %d routes to routes.yaml", written)


def _route_from_catalog_entry(entry: dict[str, Any]) -> Route:
    bbox_values = entry.get("bbox", [0.0, 0.0, 0.0, 0.0])
    bounding_box = (
        float(bbox_values[0]),
        float(bbox_values[1]),
        float(bbox_values[2]),
        float(bbox_values[3]),
    )
    landmarks = [Landmark.from_dict(item) for item in entry.get("landmarks", [])]
    pois = [
        PointOfInterest(
            name=str(poi.get("name", "")),
            lat=float(poi.get("lat", 0.0)),
            lon=float(poi.get("lon", 0.0)),
            poi_type=str(poi.get("poi_type", "")),
            url=poi.get("url") or None,
            transit_lines=list(poi.get("transit_lines", []) or []),
            distance_km=poi.get("distance_km"),
        )
        for poi in entry.get("pois", [])
    ]

    return Route(
        identifier=str(entry["id"]),
        slug=str(entry.get("slug", "")),
        path_ref=str(entry.get("path_ref", "")),
        path_name=str(entry.get("path_name", "")),
        description=str(entry.get("description", "")),
        osm_relation_id=int(entry.get("osm_relation_id", 0)),
        pois=pois,
        distance_km=float(entry.get("distance_km", 0.0)),
        elevation_gain_meters=int(entry.get("elevation_gain_m", 0)),
        elevation_loss_meters=int(entry.get("elevation_loss_m", 0)),
        max_elevation_meters=int(entry.get("max_elevation_m", 0)),
        min_elevation_meters=int(entry.get("min_elevation_m", 0)),
        bounding_box=bounding_box,
        region=str(entry.get("region", "")),
        departement=str(entry.get("departement", "")),
        difficulty=str(entry.get("difficulty", "")),
        is_circular_trail=bool(entry.get("is_circular_trail", False)),
        terrain=list(entry.get("terrain", []) or []),
        geojson_path=str(entry.get("geojson_path", "")),
        gpx_path=str(entry.get("gpx_path", "")),
        last_updated=str(entry.get("last_updated", "")),
        landmarks=landmarks,
        image_path=entry.get("image_path"),
    )
