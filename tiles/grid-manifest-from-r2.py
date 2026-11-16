#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema>=4.21"]
# ///
"""Rebuild grid.json from the bundles already uploaded to R2.

build-grid.py writes grid.json next to the PMTiles it builds, so a machine that
never ran it (or lost its data dir) cannot publish the manifest even though the
bundles are live. This script asks R2 for each bundle's size (HEAD request) and
rebuilds the manifest from the same layer specs, grid and snapshot
build-grid.py uses. The output goes through the same schema validation.

Squares with no bundle on R2 are left out and reported; build-routes.py then
refuses any route that needs one.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

_spec = importlib.util.spec_from_file_location("build_grid", SCRIPT_DIR / "build-grid.py")
assert _spec is not None and _spec.loader is not None
build_grid = importlib.util.module_from_spec(_spec)
sys.modules["build_grid"] = build_grid
_spec.loader.exec_module(build_grid)


def remote_size(url: str) -> int | None:
    """Content-Length of the object at `url`, or None when it does not exist."""
    # r2.dev answers 403 to the default Python user agent.
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "open-rando-tiles"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.headers["Content-Length"])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cols", type=int, default=build_grid.DEFAULT_COLS)
    parser.add_argument("--rows", type=int, default=build_grid.DEFAULT_ROWS)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--r2-public-url",
        default=os.environ.get("R2_PUBLIC_URL", build_grid.DEFAULT_R2_PUBLIC_URL),
    )
    parser.add_argument(
        "--data-dir",
        type=pathlib.Path,
        default=build_grid.DATA_DIR,
        help="Where to write grid.json (default: %(default)s)",
    )
    args = parser.parse_args()

    grid_bbox = build_grid.read_grid_bbox()
    snapshot = build_grid.read_makefile_var("SNAPSHOT")
    layers = build_grid.layer_specs()
    base_url = args.r2_public_url

    jobs: list[tuple[str, str, str]] = []  # (square key or "base", layer, url)
    for layer in layers:
        jobs.append(("base", layer.name, f"{base_url}/base/{layer.name}.pmtiles"))
    square_keys = [f"{col}_{row}" for col in range(args.cols) for row in range(args.rows)]
    for square_key in square_keys:
        for layer in layers:
            jobs.append((square_key, layer.name, f"{base_url}/grid/{square_key}/{layer.name}.pmtiles"))

    print(f"Checking {len(jobs)} bundles on {base_url} (snapshot {snapshot}) ...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        sizes = list(executor.map(lambda job: remote_size(job[2]), jobs))
    size_by_job = {(owner, layer): size for (owner, layer, _), size in zip(jobs, sizes, strict=True)}

    base_entries: dict[str, dict] = {}
    for layer in layers:
        size = size_by_job[("base", layer.name)]
        if size is None:
            print(f"ERROR: base/{layer.name}.pmtiles is not on R2", file=sys.stderr)
            return 1
        base_entries[layer.name] = {
            "size": size,
            "minzoom": layer.base_minzoom,
            "maxzoom": layer.base_maxzoom,
        }

    squares: dict[str, dict] = {}
    skipped: list[str] = []
    for square_key in square_keys:
        files = {
            layer.name: {
                "size": size_by_job[(square_key, layer.name)],
                "minzoom": layer.grid_minzoom,
                "maxzoom": layer.grid_maxzoom,
            }
            for layer in layers
            if size_by_job[(square_key, layer.name)] is not None
        }
        if len(files) != len(layers):
            skipped.append(square_key)
            continue
        col, row = (int(part) for part in square_key.split("_"))
        bbox = build_grid.square_bbox(col, row, args.cols, args.rows, grid_bbox)
        squares[square_key] = {"bbox": list(bbox), "files": files}

    manifest = build_grid.build_manifest(
        snapshot, grid_bbox, args.cols, args.rows, base_entries, squares
    )
    try:
        path = build_grid.write_grid_manifest(manifest, args.data_dir, base_url)
    except build_grid.tile_manifests.ManifestError as error:
        print(f"ERROR: grid.json not written. {error}", file=sys.stderr)
        return 1

    print(f"Wrote {path}: {len(squares)} squares, base layers {sorted(base_entries)}")
    if skipped:
        print(f"WARN: squares without a complete bundle on R2, left out: {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
