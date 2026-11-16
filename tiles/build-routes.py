#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema>=4.21"]
# ///
"""Write per-route grid-square manifests for mobile offline downloads.

For each route in catalog.json: find the grid squares that intersect the
route's padded bbox and emit a manifest pointing at those squares. The
actual PMTiles come from the grid extracts written by build-grid.py.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

import tile_manifests

DATA_DIR = pathlib.Path(
    os.environ.get("OPEN_RANDO_DATA_DIR")
    or pathlib.Path.home() / ".local/share/open-rando/data"
)


def pad_bbox(bbox: list[float]) -> tuple[float, float, float, float]:
    lon_min, lat_min, lon_max, lat_max = bbox
    pad_degrees = tile_manifests.PAD_DEG
    return (
        lon_min - pad_degrees,
        lat_min - pad_degrees,
        lon_max + pad_degrees,
        lat_max + pad_degrees,
    )


def route_squares(
    route_bbox: list[float],
    cols: int,
    rows: int,
    grid_bbox: tuple[float, float, float, float],
) -> list[list[int]]:
    """Return the [col, row] pairs whose square intersects the padded route bbox."""
    lon_min_g, lat_min_g, lon_max_g, lat_max_g = grid_bbox
    lon_step = (lon_max_g - lon_min_g) / cols
    lat_step = (lat_max_g - lat_min_g) / rows
    r_lon_min, r_lat_min, r_lon_max, r_lat_max = pad_bbox(route_bbox)

    # Clamp to grid so routes that spill outside the France bbox still match.
    clamped_lon_min = max(r_lon_min, lon_min_g)
    clamped_lat_min = max(r_lat_min, lat_min_g)
    clamped_lon_max = min(r_lon_max, lon_max_g)
    clamped_lat_max = min(r_lat_max, lat_max_g)
    if clamped_lon_min >= clamped_lon_max or clamped_lat_min >= clamped_lat_max:
        return []

    col_min = int((clamped_lon_min - lon_min_g) / lon_step)
    col_max = int((clamped_lon_max - lon_min_g) / lon_step)
    row_min = int((clamped_lat_min - lat_min_g) / lat_step)
    row_max = int((clamped_lat_max - lat_min_g) / lat_step)

    # Floating-point + exact-edge safety: the max index can equal cols/rows
    # when the clamped max lands exactly on the outer edge.
    col_max = min(col_max, cols - 1)
    row_max = min(row_max, rows - 1)

    return [
        [col, row]
        for col in range(col_min, col_max + 1)
        for row in range(row_min, row_max + 1)
    ]


def build_route_manifest(
    route_id: str,
    snapshot: str,
    route_bbox: list[float],
    squares: list[list[int]],
) -> dict:
    """Assemble one routes/{id}/pmtiles.json. Pure: no I/O, no validation."""
    return {
        "route_id": route_id,
        "source_snapshot": snapshot,
        "bbox": route_bbox,
        "squares": squares,
    }


def load_grid_manifest(data_dir: pathlib.Path) -> dict | None:
    """Return the built grid.json for cross-checks, or None when it is not built yet."""
    grid_path = data_dir / "grid.json"
    if not grid_path.exists():
        return None
    return json.loads(grid_path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=pathlib.Path,
        default=DATA_DIR / "catalog.json",
    )
    parser.add_argument("--cols", type=int, default=tile_manifests.DEFAULT_COLS)
    parser.add_argument("--rows", type=int, default=tile_manifests.DEFAULT_ROWS)
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=DATA_DIR,
        help=(
            "Write manifests to this data dir under routes/{id}/pmtiles.json; "
            "defaults to the pipeline data dir so the website prebuild step "
            "picks them up alongside catalog.json"
        ),
    )
    parser.add_argument(
        "--route",
        help="Only process this route id (default: all routes)",
    )
    args = parser.parse_args()

    if not args.catalog.exists():
        print(f"ERROR: catalog not found at {args.catalog}", file=sys.stderr)
        return 1

    catalog = json.loads(args.catalog.read_text())
    routes = catalog["routes"]
    if args.route:
        routes = [r for r in routes if r["id"] == args.route]
        if not routes:
            print(f"ERROR: route {args.route!r} not in catalog", file=sys.stderr)
            return 1

    grid_bbox = tile_manifests.read_grid_bbox()
    snapshot = tile_manifests.read_makefile_var("SNAPSHOT")

    routes_dir = args.out / "routes"
    routes_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"Writing {len(routes)} manifest(s), grid={args.cols}x{args.rows}, "
        f"snapshot={snapshot}, out={routes_dir}"
    )

    grid_manifest = load_grid_manifest(args.out)
    if grid_manifest is None:
        print(
            "  WARN     grid.json not found: checking manifest shape only, "
            "not that squares exist (run build-grid first)"
        )

    empty = 0
    for route in routes:
        route_id = route["id"]
        squares = route_squares(route["bbox"], args.cols, args.rows, grid_bbox)
        if not squares:
            empty += 1
            print(f"  WARN     {route_id}: bbox does not intersect grid")
        manifest = build_route_manifest(route_id, snapshot, route["bbox"], squares)
        try:
            tile_manifests.validate_route_manifest(manifest, grid_manifest)
        except tile_manifests.ManifestError as exc:
            print(f"ERROR: {route_id} manifest not written. {exc}", file=sys.stderr)
            return 1
        route_dir = routes_dir / route_id
        route_dir.mkdir(parents=True, exist_ok=True)
        (route_dir / "pmtiles.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Done: wrote {len(routes)} manifest(s), {empty} empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
