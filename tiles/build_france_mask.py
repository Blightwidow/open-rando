#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["shapely>=2", "requests>=2.31"]
# ///
"""Build metropolitan France admin boundary polygons.

Outputs:
  france-boundary.geojson — France polygon (used as gdalwarp/ogr2ogr cutline)
  france-mask.geojson     — world bbox minus France (available as style mask)

Source: Natural Earth 1:10m map_units (metropolitan France only, excludes DOM/TOM).
"""

import json
import sys
from pathlib import Path

import requests
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

NATURAL_EARTH_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_10m_admin_0_map_units.geojson"
)
SIMPLIFY_TOLERANCE = 0.005  # ~500m at France latitudes
WORLD_BBOX = (-180.0, -85.0, 180.0, 85.0)


def write_geojson(path: Path, geometry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": mapping(geometry),
        }],
    }))
    print(f"Wrote {path} ({path.stat().st_size / 1024:.1f} KB)")


def main() -> None:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

    print("Fetching Natural Earth map_units...")
    response = requests.get(NATURAL_EARTH_URL, timeout=60)
    response.raise_for_status()
    features = response.json()["features"]

    france_features = [
        feature for feature in features
        if feature["properties"].get("ADMIN") == "France"
        and feature["properties"].get("NAME") == "France"
        and feature["properties"].get("CONTINENT") == "Europe"
    ]
    if not france_features:
        raise SystemExit("France metropolitan polygon not found in Natural Earth data")

    france_geom = unary_union([shape(feature["geometry"]) for feature in france_features])
    france_simplified = france_geom.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)

    write_geojson(output_dir / "france-boundary.geojson", france_simplified)
    write_geojson(output_dir / "france-mask.geojson", box(*WORLD_BBOX).difference(france_simplified))


if __name__ == "__main__":
    main()
