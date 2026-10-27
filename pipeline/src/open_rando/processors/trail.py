"""Trail assembly shared by the `pipeline` and `tracks` commands."""

from __future__ import annotations

import time

from shapely.geometry import LineString, MultiLineString

from open_rando.config import OVERPASS_COOLDOWN_SECONDS
from open_rando.fetchers.overpass import (
    chain_linestrings,
    fetch_trail,
    order_segments_along_route,
)


def fetch_and_fuse_trails(
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
        combined = order_segments_along_route(chain_linestrings(all_linestrings))

    primary_metadata["osm_relation_id"] = relation_ids[0]
    return combined, primary_metadata, all_cached


def detect_circular_trail(trail: LineString | MultiLineString) -> bool:
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
