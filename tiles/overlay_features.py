#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Sort `osmium export` features into one GeoJSONSeq file per overlay layer.

Reads GeoJSONSeq on stdin (osmium export -f geojsonseq) and writes
`<layer>.geojsonl` into --out-dir, keeping only the tags the map style needs.
Areas that stand for a point (a shelter, a hut, a viewpoint mapped as a
building) become their centroid. Features that would clutter the map are
dropped here, not in the style: bus shelters, and water points tagged as not
drinkable.

Usage: osmium export -f geojsonseq --geometry-types=point,linestring,polygon \\
           overlay-points.osm.pbf | overlay_features.py --out-dir build-overlay \\
           --layers hut,shelter,water
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter
from typing import Any

Feature = dict[str, Any]

# Mapped as amenity=shelter but not a place a hiker can use.
EXCLUDED_SHELTER_TYPES = {"public_transport", "gazebo", "pergola", "sun_shelter", "wildlife_hide"}
MIN_ELEVATION_M = -100
MAX_ELEVATION_M = 5000

POINT_GEOMETRIES = {"Point", "Polygon", "MultiPolygon"}
LINE_GEOMETRIES = {"LineString"}

# Paths and tracks a hiker can walk over a bridge. Roads are left out: the base map draws them.
BRIDGE_HIGHWAYS = {"path", "footway", "steps", "bridleway", "cycleway", "track", "pedestrian"}
FOOT_BRIDGE_HIGHWAYS = {"path", "footway", "steps", "bridleway", "pedestrian"}
AERIALWAYS = {
    "cable_car",
    "gondola",
    "mixed_lift",
    "chair_lift",
    "drag_lift",
    "t-bar",
    "j-bar",
    "platter",
    "rope_tow",
    "magic_carpet",
    "zip_line",
}
# Christian places of worship are the landmarks wanted; a mosque or synagogue is not.
NON_CHRISTIAN_RELIGIONS = {"muslim", "jewish", "buddhist", "hindu", "sikh", "shinto", "taoist"}

Values = str | frozenset[str] | None  # None: any value of the tag

# (layer, tag, values, geometries). First match wins, so a hut also tagged as a shelter stays a hut.
RULES: list[tuple[str, str, Values, set[str]]] = [
    ("hut", "tourism", frozenset({"alpine_hut", "wilderness_hut"}), POINT_GEOMETRIES),
    ("shelter", "amenity", "shelter", POINT_GEOMETRIES),
    ("water", "amenity", frozenset({"drinking_water", "water_point"}), {"Point"}),
    ("water", "man_made", "water_tap", {"Point"}),
    ("spring", "natural", "spring", {"Point"}),
    ("guidepost", "information", "guidepost", {"Point"}),
    ("peak", "natural", "peak", {"Point"}),
    ("pass", "mountain_pass", "yes", {"Point"}),
    ("pass", "natural", "saddle", {"Point"}),
    ("waterfall", "waterway", "waterfall", {"Point"}),
    ("cave", "natural", "cave_entrance", {"Point"}),
    ("ford", "ford", "yes", {"Point"}),
    ("viewpoint", "tourism", "viewpoint", POINT_GEOMETRIES),
    ("toilets", "amenity", "toilets", POINT_GEOMETRIES),
    ("church", "amenity", "place_of_worship", POINT_GEOMETRIES),
    ("cemetery", "landuse", "cemetery", POINT_GEOMETRIES),
    ("cemetery", "amenity", "grave_yard", POINT_GEOMETRIES),
    ("power_line", "power", "line", LINE_GEOMETRIES),
    ("power_tower", "power", "tower", {"Point"}),
    ("aerialway", "aerialway", frozenset(AERIALWAYS), LINE_GEOMETRIES),
    ("river", "waterway", "river", LINE_GEOMETRIES),
    ("stream", "waterway", "stream", LINE_GEOMETRIES),
    # Last: a river or a power line that crosses on a bridge keeps its own layer.
    ("bridge", "bridge", None, LINE_GEOMETRIES),
]
# Areas mapped for these stand for a point: draw their centroid.
CENTROID_LAYERS = {"hut", "shelter", "viewpoint", "toilets", "church", "cemetery"}
ELEVATION_LAYERS = {"peak", "hut", "pass"}
LAYERS = list(dict.fromkeys(layer for layer, *_ in RULES))

# First zoom each layer is drawn at. Points are cheap, so they come in early enough to
# plan a day; towers and streams are dense and only read up close. Written on every
# feature as `tippecanoe.minzoom`: tippecanoe ignores a minzoom given per layer.
MIN_ZOOMS = {
    "river": 8,
    "peak": 9,
    "hut": 9,
    "power_line": 10,
    "aerialway": 10,
    "pass": 10,
    "water": 11,
    "spring": 11,
    "shelter": 11,
    "viewpoint": 11,
    "guidepost": 12,
    "stream": 12,
    "waterfall": 12,
    "cave": 12,
    "church": 12,
    "toilets": 13,
    "cemetery": 13,
    "ford": 13,
    "bridge": 13,
    "power_tower": 13,
}


def parse_elevation(raw: str | None) -> int | None:
    """Metres from an OSM `ele` value such as "1234", "1234.5" or "1 234 m"."""
    if not raw:
        return None
    match = re.match(r"\s*(-?\d[\d\s]*(?:[.,]\d+)?)", raw)
    if not match:
        return None
    try:
        elevation = float(match.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    if not MIN_ELEVATION_M <= elevation <= MAX_ELEVATION_M:
        return None
    return round(elevation)


def centroid(geometry: dict[str, Any]) -> dict[str, Any] | None:
    """Mean of the outer ring's vertices; precise enough for a map icon."""
    if geometry["type"] == "Point":
        return geometry
    outer_ring = (
        geometry["coordinates"][0]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"][0][0]
    )
    vertices = (
        outer_ring[:-1] if len(outer_ring) > 1 and outer_ring[0] == outer_ring[-1] else outer_ring
    )
    if not vertices:
        return None
    longitude = sum(vertex[0] for vertex in vertices) / len(vertices)
    latitude = sum(vertex[1] for vertex in vertices) / len(vertices)
    return {"type": "Point", "coordinates": [round(longitude, 6), round(latitude, 6)]}


def tag_matches(tags: dict[str, str], tag: str, values: Values) -> bool:
    actual = tags.get(tag)
    if actual is None:
        return False
    if values is None:
        return True
    if isinstance(values, str):
        return actual == values
    return actual in values


def is_excluded(layer: str, tags: dict[str, str]) -> bool:
    if layer == "shelter":
        return tags.get("shelter_type") in EXCLUDED_SHELTER_TYPES
    if layer == "water":
        return tags.get("drinking_water") == "no"
    if layer == "church":
        return tags.get("religion") in NON_CHRISTIAN_RELIGIONS
    if layer == "toilets":
        return tags.get("access") in {"private", "no", "customers"}
    if layer == "bridge":
        return tags.get("bridge") == "no" or tags.get("highway") not in BRIDGE_HIGHWAYS
    return False


def extra_properties(layer: str, tags: dict[str, str]) -> dict[str, Any]:
    """Layer-specific tags the style reads, besides `name` and `ele`."""
    if layer == "aerialway":
        return {"kind": tags["aerialway"]}
    if layer == "bridge":
        return {"kind": "foot" if tags.get("highway") in FOOT_BRIDGE_HIGHWAYS else "track"}
    return {}


def classify(feature: Feature) -> tuple[str, Feature] | None:
    """The overlay layer a feature belongs to and the feature to write, or None to drop it."""
    tags: dict[str, str] = feature.get("properties") or {}
    geometry = feature.get("geometry")
    if not geometry:
        return None

    for layer, tag, values, geometries in RULES:
        if not tag_matches(tags, tag, values) or geometry["type"] not in geometries:
            continue
        if is_excluded(layer, tags):
            return None
        if layer in CENTROID_LAYERS:
            geometry = centroid(geometry)
            if geometry is None:
                return None

        properties: dict[str, Any] = {}
        if tags.get("name"):
            properties["name"] = tags["name"]
        if layer in ELEVATION_LAYERS:
            elevation = parse_elevation(tags.get("ele"))
            if elevation is not None:
                properties["ele"] = elevation
        properties.update(extra_properties(layer, tags))
        return layer, {
            "type": "Feature",
            "properties": properties,
            "geometry": geometry,
            "tippecanoe": {"minzoom": MIN_ZOOMS[layer]},
        }
    return None


def split_features(lines: Any, out_dir: pathlib.Path, layers: list[str]) -> Counter[str]:
    """Write each classified feature of `layers` to its layer file; returns the count per layer.

    Only the given layers are (re)written, so each source extract can own its own layers.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    handles = {
        layer: (out_dir / f"{layer}.geojsonl").open("w", encoding="utf-8") for layer in layers
    }
    try:
        for line in lines:
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            classified = classify(json.loads(line))
            if classified is None:
                continue
            layer, feature = classified
            if layer not in handles:
                continue
            handles[layer].write(
                json.dumps(feature, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            counts[layer] += 1
    finally:
        for handle in handles.values():
            handle.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument(
        "--layers",
        required=True,
        help=f"Comma-separated layers to write, from: {', '.join(LAYERS)}",
    )
    args = parser.parse_args()
    layers = args.layers.split(",")
    unknown = sorted(set(layers) - set(LAYERS))
    if unknown:
        parser.error(f"unknown layers: {', '.join(unknown)}")
    counts = split_features(sys.stdin, args.out_dir, layers)
    for layer in layers:
        if counts[layer]:
            print(f"  {layer}: {counts[layer]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
