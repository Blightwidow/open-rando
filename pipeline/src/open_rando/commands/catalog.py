"""`catalog` subcommand — assemble catalog.json from tracks and links.

Reads every `tracks/<id>/track.json` and its `links/<id>.json`, keeps the
tracks with enough linked train stations, and writes the catalog plus a run
report comparing it with the previous catalog.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from open_rando.config import (
    CATALOG_PATH,
    FAILURE_LOG_PATH,
    LINKS_DIRECTORY,
    MIN_TRAIN_STATIONS_PER_ROUTE,
    RUN_REPORT_PATH,
    TRACKS_DIRECTORY,
)
from open_rando.exporters.catalog import export_route_catalog
from open_rando.exporters.failures import load_failure_log
from open_rando.exporters.image_generator import find_image_on_disk
from open_rando.exporters.links import load_link_counts
from open_rando.exporters.report import build_run_report, export_run_report, log_run_report
from open_rando.exporters.track import TRACK_METADATA_FILE_NAME, load_track_metadata
from open_rando.models import Track

logger = logging.getLogger("open_rando")


def add_catalog_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "catalog",
        help="Assemble catalog.json from the computed tracks and their links.",
    )
    parser.set_defaults(func=run_catalog)


def build_catalog_entries(
    tracks: list[Track],
    counts_by_track: dict[str, dict[str, int]],
    image_paths: dict[int, str],
    image_on_disk: Any,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Catalog entries, plus the refs left out for too few stations and for no links.

    image_paths maps an OSM relation id to the image path of the previous
    catalog; image_on_disk(track_id) recovers images a --reset run would orphan.
    """
    entries: list[dict[str, Any]] = []
    too_few_stations: list[str] = []
    unlinked: list[str] = []

    for track in sorted(tracks, key=lambda candidate: candidate.path_ref):
        counts = counts_by_track.get(track.identifier)
        if counts is None:
            unlinked.append(track.path_ref)
            continue
        if counts["train_station"] < MIN_TRAIN_STATIONS_PER_ROUTE:
            too_few_stations.append(track.path_ref)
            continue

        entry = track.to_dict()
        entry["poi_counts"] = counts
        image_path = image_paths.get(track.osm_relation_id) or image_on_disk(track.identifier)
        if image_path:
            entry["image_path"] = image_path
        entries.append(entry)

    return entries, too_few_stations, unlinked


def run_catalog(_arguments: argparse.Namespace) -> None:
    tracks_directory = Path(TRACKS_DIRECTORY).expanduser()
    links_directory = Path(LINKS_DIRECTORY).expanduser()
    catalog_path = Path(CATALOG_PATH).expanduser()

    tracks = [
        load_track_metadata(path.parent)
        for path in sorted(tracks_directory.glob(f"*/{TRACK_METADATA_FILE_NAME}"))
    ]
    if not tracks:
        raise SystemExit("No computed track. Run `python -m open_rando tracks` first.")

    counts_by_track = {
        track.identifier: load_link_counts(track.identifier, links_directory)
        for track in tracks
        if (links_directory / f"{track.identifier}.json").exists()
    }

    previous_routes: list[dict[str, Any]] = []
    if catalog_path.exists():
        previous_routes = json.loads(catalog_path.read_text(encoding="utf-8")).get("routes", [])
    image_paths = {
        int(entry["osm_relation_id"]): str(entry["image_path"])
        for entry in previous_routes
        if entry.get("image_path")
    }

    entries, too_few_stations, unlinked = build_catalog_entries(
        tracks, counts_by_track, image_paths, find_image_on_disk
    )
    export_route_catalog(entries, str(catalog_path))

    failure_log = load_failure_log(str(Path(FAILURE_LOG_PATH).expanduser()))
    report = build_run_report(
        previous_routes=previous_routes,
        current_routes=entries,
        failed_route_refs=list(failure_log),
        skipped_route_refs=[*too_few_stations, *unlinked],
    )
    report_path = str(Path(RUN_REPORT_PATH).expanduser())
    export_run_report(report, report_path)

    logger.info("=== Summary ===")
    logger.info("Tracks in catalog: %d of %d computed", len(entries), len(tracks))
    if too_few_stations:
        logger.warning(
            "Left out, fewer than %d train stations: %s",
            MIN_TRAIN_STATIONS_PER_ROUTE,
            ", ".join(too_few_stations),
        )
    if unlinked:
        logger.warning("Left out, not linked yet (run `link`): %s", ", ".join(unlinked))
    logger.info("Catalog written to %s", catalog_path)
    log_run_report(report)
    logger.info("Run report written to %s", report_path)
