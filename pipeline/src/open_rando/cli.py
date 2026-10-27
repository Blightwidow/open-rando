from __future__ import annotations

import argparse
import logging
from pathlib import Path

from open_rando.commands.catalog import add_catalog_subparser, run_catalog
from open_rando.commands.gtfs import add_gtfs_subparser, run_gtfs
from open_rando.commands.images import add_images_subparser
from open_rando.commands.link import add_link_subparser, run_link
from open_rando.commands.osm_index import add_osm_index_subparser
from open_rando.commands.pois import add_pois_subparser, run_pois
from open_rando.commands.tracks import add_tracks_subparser, run_tracks
from open_rando.config import FAILURE_LOG_PATH, TRACKS_DIRECTORY
from open_rando.exporters.failures import load_failure_log
from open_rando.exporters.track import TRACK_METADATA_FILE_NAME, load_track_metadata
from open_rando.poi_grid import PoiGrid
from open_rando.processors.link import CANDIDATE_BUFFER_DEGREES

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("open_rando")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="open-rando — GR tracks, POI grid, catalog + image generation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Run every stage: tracks, gtfs, pois, link, catalog.",
    )
    pipeline_parser.add_argument(
        "--route",
        type=str,
        help="Process a single route by ref (e.g. 'GR 13'); builds only its POI squares.",
    )
    pipeline_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List discovered routes without processing them.",
    )
    pipeline_parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Only process routes that failed in a previous run "
        "(listed in data/failed-routes.json).",
    )
    pipeline_parser.add_argument(
        "--skip-gtfs",
        action="store_true",
        help="Skip the `gtfs` download stage and reuse the existing stop index.",
    )
    pipeline_parser.set_defaults(func=run_pipeline)

    add_tracks_subparser(subparsers)
    add_gtfs_subparser(subparsers)
    add_pois_subparser(subparsers)
    add_link_subparser(subparsers)
    add_catalog_subparser(subparsers)
    add_images_subparser(subparsers)
    add_osm_index_subparser(subparsers)

    arguments = parser.parse_args()
    arguments.func(arguments)


def run_pipeline(arguments: argparse.Namespace) -> None:
    """tracks -> gtfs -> pois -> link -> catalog, each stage as its own command would run."""
    failed_refs = set(load_failure_log(str(Path(FAILURE_LOG_PATH).expanduser())))

    run_tracks(
        argparse.Namespace(
            route=arguments.route,
            dry_run=arguments.dry_run,
            retry_failed=arguments.retry_failed,
        )
    )
    if arguments.dry_run:
        return

    if not arguments.skip_gtfs:
        run_gtfs(argparse.Namespace(resource=None, refresh=False, status=False))

    scoped_refs = {arguments.route} if arguments.route else failed_refs
    scoped = bool(arguments.route or arguments.retry_failed)
    run_pois(
        argparse.Namespace(
            square=square_names_for_tracks(scoped_refs) if scoped else None,
            skip_gtfs=False,
        )
    )
    run_link(argparse.Namespace(route=arguments.route, skip_walking_refinement=False))
    run_catalog(argparse.Namespace())


def square_names_for_tracks(refs: set[str]) -> list[str]:
    """POI grid squares ("col_row") that the given tracks touch, with the link margin."""
    grid = PoiGrid()
    squares: set[tuple[int, int]] = set()
    tracks_directory = Path(TRACKS_DIRECTORY).expanduser()
    for metadata_path in tracks_directory.glob(f"*/{TRACK_METADATA_FILE_NAME}"):
        track = load_track_metadata(metadata_path.parent)
        if track.path_ref in refs:
            squares.update(
                grid.squares_for_bounding_box(track.bounding_box, CANDIDATE_BUFFER_DEGREES)
            )
    return [f"{column}_{row}" for column, row in sorted(squares)]
