"""`gtfs` subcommand — download every national GTFS feed once.

One pass per feed fills two local stores: the stop index (queried by the
`pois` stage) and the per-feed departures cache (read by the GTFS enrichment).
No per-area API calls: the feed list comes from a single catalog request.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from open_rando.config import GTFS_CACHE_TTL_SECONDS
from open_rando.fetchers.gtfs import (
    FEED_STATUS_DOWNLOAD_FAILED,
    FEED_STATUS_INDEXED,
    fetch_resource_url_map,
    index_feed,
)
from open_rando.fetchers.gtfs_stops_index import GtfsStopsIndex

logger = logging.getLogger("open_rando")


def add_gtfs_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "gtfs",
        help="Download every national GTFS feed and build the local stop index.",
    )
    parser.add_argument(
        "--resource",
        action="append",
        type=int,
        metavar="ID",
        help="Index only this transport.data.gouv.fr resource id (repeatable).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-download feeds even when they were indexed recently.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report what the index holds and exit.",
    )
    parser.set_defaults(func=run_gtfs)


def run_gtfs(arguments: argparse.Namespace) -> None:
    if arguments.status:
        _report_status()
        return

    resource_url_map = fetch_resource_url_map()
    if arguments.resource:
        resource_url_map = {
            resource_id: url
            for resource_id, url in resource_url_map.items()
            if resource_id in arguments.resource
        }

    index = GtfsStopsIndex.open_for_writing()
    reference_date = date.today()
    indexed = skipped = failed = 0
    try:
        for position, (resource_id, url) in enumerate(sorted(resource_url_map.items()), start=1):
            if not arguments.refresh and index.is_feed_fresh(resource_id, GTFS_CACHE_TTL_SECONDS):
                skipped += 1
                continue
            logger.info("[%d/%d] GTFS feed %d", position, len(resource_url_map), resource_id)
            result = index_feed(resource_id, url, reference_date)
            if result.status == FEED_STATUS_DOWNLOAD_FAILED:
                # Not recorded: a transient failure is retried on the next run.
                failed += 1
                continue
            index.replace_feed(resource_id, result.status, result.stops)
            if result.status == FEED_STATUS_INDEXED:
                indexed += 1
            logger.info("  -> %s, %d stops", result.status, len(result.stops))
    finally:
        index.close()

    logger.info(
        "=== GTFS: %d indexed, %d already fresh, %d download failures ===",
        indexed,
        skipped,
        failed,
    )
    if failed:
        logger.warning("Rerun `gtfs` to retry the %d failed download(s)", failed)


def _report_status() -> None:
    index = GtfsStopsIndex.open_for_reading()
    if index is None:
        logger.info("No GTFS stop index yet. Run `python -m open_rando gtfs`.")
        return
    try:
        logger.info("GTFS stop index: %d feeds, %d stops", index.feed_count(), index.stop_count())
    finally:
        index.close()
