"""`link` subcommand — join the POI grid to each computed track.

Reads `tracks/<id>/` and `pois/`, writes `links/<id>.json`. Relinking is cheap:
change a distance threshold and rerun, no refetch of trails or POIs.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, shape

from open_rando.config import (
    LINKS_DIRECTORY,
    MIN_TRAIN_STATIONS_PER_ROUTE,
    POIS_DIRECTORY,
    TRACKS_DIRECTORY,
)
from open_rando.exporters.links import export_links
from open_rando.exporters.track import (
    TRACK_METADATA_FILE_NAME,
    TRAIL_GEOJSON_FILE_NAME,
    load_track_metadata,
)
from open_rando.models import Track
from open_rando.poi_grid import PoiGrid
from open_rando.poi_store import PoiGridMissingError, read_poi_squares
from open_rando.processors.link import (
    CANDIDATE_BUFFER_DEGREES,
    link_pois_to_trail,
    summarize_links,
)

logger = logging.getLogger("open_rando")


def add_link_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "link",
        help="Join the POI grid to each computed track (links/<id>.json).",
    )
    parser.add_argument("--route", type=str, help="Link a single track by ref ('GR 13').")
    parser.add_argument(
        "--skip-walking-refinement",
        action="store_true",
        help="Keep the perpendicular junction instead of querying OSRM walking distances.",
    )
    parser.set_defaults(func=run_link)


def load_trail(track_directory: Path) -> LineString | MultiLineString:
    collection = json.loads((track_directory / TRAIL_GEOJSON_FILE_NAME).read_text(encoding="utf-8"))
    trail_feature = next(
        feature
        for feature in collection["features"]
        if feature["properties"].get("feature_type") == "trail"
    )
    geometry = shape(trail_feature["geometry"])
    if not isinstance(geometry, LineString | MultiLineString):
        raise ValueError(f"Trail of {track_directory} is a {geometry.geom_type}")
    return geometry


def link_track(
    track: Track,
    track_directory: Path,
    pois_directory: Path,
    links_directory: Path,
    refine_junctions: bool,
) -> int:
    """Link one track and write its file. Returns the linked train station count."""
    grid = PoiGrid()
    squares = grid.squares_for_bounding_box(track.bounding_box, CANDIDATE_BUFFER_DEGREES)
    pois = read_poi_squares(pois_directory, grid, squares)
    logger.info("  %d squares, %d POIs loaded", len(squares), len(pois))

    links = link_pois_to_trail(load_trail(track_directory), pois, refine_junctions)
    counts = summarize_links(links, pois)
    export_links(track.identifier, links, counts, links_directory)
    logger.info("  -> %s", ", ".join(f"{count} {kind}" for kind, count in counts.items()))
    return counts["train_station"]


def run_link(arguments: argparse.Namespace) -> None:
    tracks_directory = Path(TRACKS_DIRECTORY).expanduser()
    pois_directory = Path(POIS_DIRECTORY).expanduser()
    links_directory = Path(LINKS_DIRECTORY).expanduser()

    track_directories = sorted(
        path.parent for path in tracks_directory.glob(f"*/{TRACK_METADATA_FILE_NAME}")
    )
    tracks = [(load_track_metadata(directory), directory) for directory in track_directories]
    if arguments.route:
        tracks = [
            (track, directory) for track, directory in tracks if track.path_ref == arguments.route
        ]
    if not tracks:
        raise SystemExit(
            "No computed track to link. Run `python -m open_rando tracks` first"
            + (f" (looked for '{arguments.route}')." if arguments.route else ".")
        )

    for position, (track, track_directory) in enumerate(tracks, start=1):
        logger.info("=== [%d/%d] Linking %s ===", position, len(tracks), track.path_ref)
        try:
            train_station_count = link_track(
                track,
                track_directory,
                pois_directory,
                links_directory,
                refine_junctions=not arguments.skip_walking_refinement,
            )
        except PoiGridMissingError as error:
            raise SystemExit(str(error)) from error
        if train_station_count < MIN_TRAIN_STATIONS_PER_ROUTE:
            logger.warning(
                "  Only %d train stations (need %d): the catalog will leave this track out",
                train_station_count,
                MIN_TRAIN_STATIONS_PER_ROUTE,
            )
