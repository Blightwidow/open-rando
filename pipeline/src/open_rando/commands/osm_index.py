"""Build the local OSM extract index from Geofabrik PBF extracts.

`make -f Makefile.osm` downloads france-latest.osm.pbf and splits it into the
per-layer extracts this command reads. Only this module needs pyosmium; the
pipeline itself queries the resulting SQLite index.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from open_rando.config import OSM_EXTRACT_DIRECTORY
from open_rando.fetchers.osm_extract import (
    ALL_LAYERS,
    LAYER_ACCOMMODATION,
    LAYER_FOREST,
    LAYER_LANDMARKS,
    LAYER_STATIONS,
    LAYER_TRAILS,
    OsmExtractIndex,
    is_accommodation_tagged,
    is_forest_tagged,
    is_station_tagged,
    is_trail_relation_tagged,
    landmark_kind_for_tags,
)

logger = logging.getLogger("open_rando")

BATCH_SIZE = 20_000

EXTRACT_FILENAMES = {
    LAYER_STATIONS: "stations.osm.pbf",
    LAYER_ACCOMMODATION: "accommodation.osm.pbf",
    LAYER_LANDMARKS: "landmarks.osm.pbf",
    LAYER_FOREST: "forest.osm.pbf",
    LAYER_TRAILS: "trails.osm.pbf",
}


def add_osm_index_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    parser = subparsers.add_parser(
        "osm-index",
        help="Build the local OSM extract index used instead of Overpass.",
    )
    parser.add_argument(
        "--extracts-dir",
        type=str,
        default=OSM_EXTRACT_DIRECTORY,
        help="Directory holding the per-layer .osm.pbf extracts.",
    )
    parser.add_argument(
        "--layer",
        action="append",
        choices=list(ALL_LAYERS),
        help="Build only this layer (repeatable). Default: every layer present.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report what the index currently holds and exit.",
    )
    parser.set_defaults(func=run_osm_index)


def run_osm_index(arguments: argparse.Namespace) -> None:
    if arguments.status:
        _report_status()
        return

    extracts_directory = Path(arguments.extracts_dir).expanduser()
    layers = arguments.layer or list(ALL_LAYERS)

    index = OsmExtractIndex.open_for_writing()
    try:
        for layer in layers:
            extract_path = extracts_directory / EXTRACT_FILENAMES[layer]
            if not extract_path.exists():
                logger.warning("Skipping %s: %s not found", layer, extract_path)
                continue

            logger.info("=== Building %s from %s ===", layer, extract_path.name)
            index.clear_layer(layer)
            feature_count = build_layer(index, layer, extract_path)
            index.commit()
            index.record_layer(layer, feature_count, extract_path.name, extract_bbox(extract_path))
            logger.info("Indexed %d %s features", feature_count, layer)
    finally:
        index.close()

    _report_status()


def _report_status() -> None:
    index = OsmExtractIndex.open_for_reading()
    if index is None:
        logger.info("No OSM extract index yet — fetchers will use Overpass")
        return
    try:
        summary = index.layer_summary()
        if not summary:
            logger.info("OSM extract index at %s is empty", index.path)
            return
        logger.info("OSM extract index at %s:", index.path)
        for layer, details in summary.items():
            bbox = details.get("bbox")
            coverage = (
                "any bbox"
                if bbox is None
                else (
                    f"({bbox['south']:.2f},{bbox['west']:.2f})-"
                    f"({bbox['north']:.2f},{bbox['east']:.2f})"
                )
            )
            logger.info(
                "  %-14s %8d features from %s, covers %s, built %s",
                layer,
                details["features"],
                details["source"],
                coverage,
                details.get("built_at", "unknown"),
            )
        missing = [layer for layer in ALL_LAYERS if layer not in summary]
        if missing:
            logger.info("  missing layers (Overpass fallback): %s", ", ".join(missing))
    finally:
        index.close()


def extract_bbox(extract_path: Path) -> tuple[float, float, float, float] | None:
    """Bounding box declared in the PBF header, as (south, west, north, east).

    Geofabrik stamps it on every extract. Without it the index cannot tell a
    France-wide extract from a regional one, so coverage is left unrecorded and
    the index is trusted for any bbox.
    """
    import osmium

    box = osmium.FileProcessor(str(extract_path)).header.box()
    if not box.valid():
        logger.warning("%s has no bounding box in its header", extract_path.name)
        return None
    return (box.bottom_left.lat, box.bottom_left.lon, box.top_right.lat, box.top_right.lon)


def build_layer(index: OsmExtractIndex, layer: str, extract_path: Path) -> int:
    if layer == LAYER_STATIONS:
        return _build_point_layer(index, layer, extract_path, is_station_tagged)
    if layer == LAYER_ACCOMMODATION:
        return _build_point_layer(index, layer, extract_path, is_accommodation_tagged)
    if layer == LAYER_LANDMARKS:
        return _build_point_layer(
            index,
            layer,
            extract_path,
            lambda tags: landmark_kind_for_tags(tags) is not None,
        )
    if layer == LAYER_FOREST:
        return _build_forest_layer(index, extract_path)
    if layer == LAYER_TRAILS:
        return _build_trail_layer(index, extract_path)
    raise ValueError(f"Unknown layer: {layer}")


def _tags_dict(tags: Any) -> dict[str, str]:
    return {tag.k: tag.v for tag in tags}


def _way_coordinates(way: Any) -> list[tuple[float, float]]:
    """Coordinates of a way as (lat, lon), skipping nodes without a location."""
    coordinates: list[tuple[float, float]] = []
    for node in way.nodes:
        try:
            location = node.location
        except Exception:  # noqa: BLE001 - pyosmium raises on invalid locations
            continue
        if not location.valid():
            continue
        coordinates.append((location.lat, location.lon))
    return coordinates


def _bbox_center(coordinates: list[tuple[float, float]]) -> tuple[float, float]:
    """Center of the bounding box, matching what Overpass `out center` returns."""
    latitudes = [latitude for latitude, _longitude in coordinates]
    longitudes = [longitude for _latitude, longitude in coordinates]
    return (
        (min(latitudes) + max(latitudes)) / 2,
        (min(longitudes) + max(longitudes)) / 2,
    )


def _build_point_layer(
    index: OsmExtractIndex,
    layer: str,
    extract_path: Path,
    matches: Any,
) -> int:
    import osmium

    total = 0
    batch: list[tuple[str, int, float, float, dict[str, str]]] = []

    processor = osmium.FileProcessor(
        str(extract_path), osmium.osm.NODE | osmium.osm.WAY
    ).with_locations()

    for entity in processor:
        tags = _tags_dict(entity.tags)
        if not matches(tags):
            continue

        if isinstance(entity, osmium.osm.Node):
            location = entity.location
            if not location.valid():
                continue
            batch.append(("node", entity.id, location.lat, location.lon, tags))
        elif isinstance(entity, osmium.osm.Way):
            coordinates = _way_coordinates(entity)
            if not coordinates:
                continue
            latitude, longitude = _bbox_center(coordinates)
            batch.append(("way", entity.id, latitude, longitude, tags))
        else:
            continue

        if len(batch) >= BATCH_SIZE:
            total += index.insert_points(layer, batch)
            index.commit()
            batch.clear()

    total += index.insert_points(layer, batch)
    return total


def _build_forest_layer(index: OsmExtractIndex, extract_path: Path) -> int:
    """Index forest rings from tagged ways and from multipolygon members.

    `processors.geography` treats every ring as its own polygon, so relation
    members are stored the same way as standalone ways.
    """
    import osmium

    member_way_ids: set[int] = set()
    relation_processor = osmium.FileProcessor(str(extract_path), osmium.osm.RELATION)
    for relation in relation_processor:
        if not isinstance(relation, osmium.osm.Relation):
            continue
        if not is_forest_tagged(_tags_dict(relation.tags)):
            continue
        for member in relation.members:
            if member.type == "w":
                member_way_ids.add(int(member.ref))

    logger.info("Forest multipolygons reference %d member ways", len(member_way_ids))

    total = 0
    batch: list[tuple[str, int, list[tuple[float, float]]]] = []
    # Nodes must be read for the location cache; the loop skips them.
    way_processor = osmium.FileProcessor(
        str(extract_path), osmium.osm.NODE | osmium.osm.WAY
    ).with_locations()

    for way in way_processor:
        if not isinstance(way, osmium.osm.Way):
            continue
        if way.id not in member_way_ids and not is_forest_tagged(_tags_dict(way.tags)):
            continue
        coordinates = _way_coordinates(way)
        if len(coordinates) < 4:
            continue
        batch.append(("way", way.id, coordinates))

        if len(batch) >= BATCH_SIZE:
            total += index.insert_areas(LAYER_FOREST, batch)
            index.commit()
            batch.clear()

    total += index.insert_areas(LAYER_FOREST, batch)
    return total


def _build_trail_layer(index: OsmExtractIndex, extract_path: Path) -> int:
    """Index route relations, their members, and the geometry of member ways."""
    import osmium

    relation_rows: list[tuple[int, dict[str, str], list[dict[str, Any]]]] = []
    needed_way_ids: set[int] = set()

    relation_processor = osmium.FileProcessor(str(extract_path), osmium.osm.RELATION)
    for relation in relation_processor:
        if not isinstance(relation, osmium.osm.Relation):
            continue
        tags = _tags_dict(relation.tags)
        if not is_trail_relation_tagged(tags):
            continue
        members: list[dict[str, Any]] = [
            {"type": _member_type(member.type), "ref": int(member.ref), "role": member.role}
            for member in relation.members
        ]
        relation_rows.append((relation.id, tags, members))
        needed_way_ids.update(int(member["ref"]) for member in members if member["type"] == "way")

    relation_count = index.insert_trail_relations(relation_rows)
    index.commit()
    logger.info(
        "Indexed %d route relations referencing %d ways", relation_count, len(needed_way_ids)
    )

    way_count = 0
    batch: list[tuple[int, list[tuple[float, float]]]] = []
    # Nodes must be read for the location cache; the loop skips them.
    way_processor = osmium.FileProcessor(
        str(extract_path), osmium.osm.NODE | osmium.osm.WAY
    ).with_locations()

    for way in way_processor:
        if not isinstance(way, osmium.osm.Way):
            continue
        if way.id not in needed_way_ids:
            continue
        coordinates = _way_coordinates(way)
        if len(coordinates) < 2:
            continue
        batch.append((way.id, coordinates))

        if len(batch) >= BATCH_SIZE:
            way_count += index.insert_trail_ways(batch)
            index.commit()
            batch.clear()

    way_count += index.insert_trail_ways(batch)
    logger.info("Indexed geometry for %d member ways", way_count)
    return relation_count


def _member_type(raw: str) -> str:
    return {"n": "node", "w": "way", "r": "relation"}.get(raw, raw)
