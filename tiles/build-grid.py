#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Slice master PMTiles archives into shared low-zoom base + grid squares.

Each layer is split into two pieces:
  - base/{layer}.pmtiles   low zooms, full France, one file shared by every route
  - grid/{col}_{row}/{layer}.pmtiles   high zooms, per-square

The split eliminates the dominant cost of the naive grid approach: low-zoom
tiles are bigger than a grid square, so minzoom=8 extraction duplicated each
z8 contour tile across several adjacent squares. Hoisting z8-10 into a single
shared base file drops the per-square footprint and keeps total R2 under the
10 GB free tier.

Incremental: base and each square are rebuilt only when their bbox/zoom/
snapshot state changes (tracked in .build-state.json).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = pathlib.Path(
    os.environ.get("OPEN_RANDO_DATA_DIR")
    or pathlib.Path.home() / ".local/share/open-rando/data"
)
PAD_DEG = 0.02  # ~2 km; MapLibre has edge tiles when viewport straddles squares
DEFAULT_R2_PUBLIC_URL = "https://pub-8869314668be498091e185b1a6fe798d.r2.dev"
DEFAULT_COLS = 12
DEFAULT_ROWS = 8


@dataclass(frozen=True)
class LayerSpec:
    name: str
    source: pathlib.Path
    base_minzoom: int
    base_maxzoom: int
    grid_minzoom: int
    grid_maxzoom: int


def layer_specs() -> list[LayerSpec]:
    # Low zooms live in the shared base file (one per layer, whole France);
    # high zooms live per-square. Contours capped at z13 to fit under 10 GB
    # R2 free tier; trail overlay renders on top so sub-z13 contour detail is
    # not load-bearing for offline hiking UX.
    return [
        LayerSpec(
            name="france",
            source=SCRIPT_DIR / "france.pmtiles",
            base_minzoom=6,
            base_maxzoom=10,
            grid_minzoom=11,
            grid_maxzoom=13,
        ),
        LayerSpec(
            name="contours",
            source=DATA_DIR / "contours.pmtiles",
            base_minzoom=8,
            base_maxzoom=10,
            grid_minzoom=11,
            grid_maxzoom=13,
        ),
        LayerSpec(
            name="hillshade",
            source=DATA_DIR / "hillshade.pmtiles",
            base_minzoom=6,
            base_maxzoom=8,
            grid_minzoom=9,
            grid_maxzoom=11,
        ),
    ]


def read_makefile_var(name: str) -> str:
    makefile = SCRIPT_DIR / "Makefile.protomaps"
    match = re.search(
        rf"^{re.escape(name)}\s*:=\s*(.+?)\s*$",
        makefile.read_text(),
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"cannot find {name} in {makefile}")
    return match.group(1)


def read_grid_bbox() -> tuple[float, float, float, float]:
    """Parse BBOX from Makefile.protomaps so grid bbox tracks the master."""
    raw = read_makefile_var("BBOX")
    parts = [float(x) for x in raw.split(",")]
    if len(parts) != 4:
        raise RuntimeError(f"unexpected BBOX in Makefile.protomaps: {raw!r}")
    lon_min, lat_min, lon_max, lat_max = parts
    return lon_min, lat_min, lon_max, lat_max


def square_bbox(
    col: int,
    row: int,
    cols: int,
    rows: int,
    grid_bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    lon_min, lat_min, lon_max, lat_max = grid_bbox
    lon_step = (lon_max - lon_min) / cols
    lat_step = (lat_max - lat_min) / rows
    return (
        lon_min + col * lon_step,
        lat_min + row * lat_step,
        lon_min + (col + 1) * lon_step,
        lat_min + (row + 1) * lat_step,
    )


def pad(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    lon_min, lat_min, lon_max, lat_max = bbox
    return (lon_min - PAD_DEG, lat_min - PAD_DEG, lon_max + PAD_DEG, lat_max + PAD_DEG)


def zoom_state_hash(
    bbox: tuple[float, float, float, float],
    snapshot: str,
    minzoom: int,
    maxzoom: int,
) -> str:
    payload = json.dumps(
        {
            "bbox": [f"{x:.7f}" for x in bbox],
            "snapshot": snapshot,
            "minzoom": minzoom,
            "maxzoom": maxzoom,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def run_extract(
    pmtiles_bin: pathlib.Path,
    source: pathlib.Path,
    dest: pathlib.Path,
    bbox: tuple[float, float, float, float],
    minzoom: int,
    maxzoom: int,
) -> None:
    dest_tmp = dest.with_suffix(".pmtiles.tmp")
    bbox_arg = ",".join(f"{x:.6f}" for x in bbox)
    subprocess.run(
        [
            str(pmtiles_bin),
            "extract",
            str(source),
            str(dest_tmp),
            f"--bbox={bbox_arg}",
            f"--minzoom={minzoom}",
            f"--maxzoom={maxzoom}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    dest_tmp.replace(dest)


def build_base(
    grid_bbox: tuple[float, float, float, float],
    out_dir: pathlib.Path,
    snapshot: str,
    pmtiles_bin: pathlib.Path,
    force: bool,
) -> tuple[dict[str, dict], int, int]:
    """Build base/<layer>.pmtiles for each layer. Return (entries, built, skipped)."""
    base_dir = out_dir / "base"
    base_dir.mkdir(parents=True, exist_ok=True)
    state_path = base_dir / ".build-state.json"
    prev_state: dict[str, str] = {}
    if state_path.exists():
        try:
            prev_state = json.loads(state_path.read_text())
        except json.JSONDecodeError:
            prev_state = {}

    entries: dict[str, dict] = {}
    new_state: dict[str, str] = {}
    built = 0
    skipped = 0
    for layer in layer_specs():
        h = zoom_state_hash(grid_bbox, snapshot, layer.base_minzoom, layer.base_maxzoom)
        new_state[layer.name] = h
        dst = base_dir / f"{layer.name}.pmtiles"
        if not force and prev_state.get(layer.name) == h and dst.exists():
            skipped += 1
            print(f"  skipped  base/{layer.name}")
        else:
            try:
                run_extract(
                    pmtiles_bin,
                    layer.source,
                    dst,
                    grid_bbox,
                    layer.base_minzoom,
                    layer.base_maxzoom,
                )
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(
                    f"pmtiles extract base/{layer.name}: "
                    f"{exc.stderr.strip()[:400]}"
                )
            built += 1
            print(f"  built    base/{layer.name}")
        entries[layer.name] = {
            "size": dst.stat().st_size,
            "minzoom": layer.base_minzoom,
            "maxzoom": layer.base_maxzoom,
        }

    state_path.write_text(json.dumps(new_state, sort_keys=True) + "\n")
    return entries, built, skipped


def build_square(
    col: int,
    row: int,
    cols: int,
    rows: int,
    grid_bbox: tuple[float, float, float, float],
    out_dir: pathlib.Path,
    snapshot: str,
    pmtiles_bin: pathlib.Path,
    force: bool,
) -> tuple[str, str, dict]:
    """Return (square_key, status, square_entry)."""
    square_key = f"{col}_{row}"
    square_dir = out_dir / square_key
    bbox = square_bbox(col, row, cols, rows, grid_bbox)
    padded = pad(bbox)

    state_path = square_dir / ".build-state.json"
    prev_state: dict[str, str] = {}
    if state_path.exists():
        try:
            prev_state = json.loads(state_path.read_text())
        except json.JSONDecodeError:
            prev_state = {}

    square_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, dict] = {}
    new_state: dict[str, str] = {}
    built_any = False
    for layer in layer_specs():
        h = zoom_state_hash(padded, snapshot, layer.grid_minzoom, layer.grid_maxzoom)
        new_state[layer.name] = h
        dst = square_dir / f"{layer.name}.pmtiles"

        if not force and prev_state.get(layer.name) == h and dst.exists():
            pass
        else:
            try:
                run_extract(
                    pmtiles_bin,
                    layer.source,
                    dst,
                    padded,
                    layer.grid_minzoom,
                    layer.grid_maxzoom,
                )
            except subprocess.CalledProcessError as exc:
                return (
                    square_key,
                    f"error: pmtiles extract {layer.name}: {exc.stderr.strip()[:400]}",
                    {},
                )
            built_any = True

        files[layer.name] = {
            "size": dst.stat().st_size,
            "minzoom": layer.grid_minzoom,
            "maxzoom": layer.grid_maxzoom,
        }

    state_path.write_text(json.dumps(new_state, sort_keys=True) + "\n")

    entry = {
        "bbox": list(bbox),
        "files": files,
    }
    return square_key, ("built" if built_any else "skipped"), entry


def write_grid_manifest(
    manifest: dict,
    data_dir: pathlib.Path,
    r2_public_url: str,
) -> pathlib.Path:
    """Inject URLs + write grid.json into the pipeline data dir."""
    for layer_name, layer_entry in manifest["base"].items():
        layer_entry["url"] = f"{r2_public_url}/base/{layer_name}.pmtiles"
    for square_key, entry in manifest["squares"].items():
        for layer_name, layer_entry in entry["files"].items():
            layer_entry["url"] = (
                f"{r2_public_url}/grid/{square_key}/{layer_name}.pmtiles"
            )
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "grid.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=SCRIPT_DIR / "build-grid",
        help="Output directory for base/ + per-square PMTiles (default: %(default)s)",
    )
    parser.add_argument("--cols", type=int, default=DEFAULT_COLS)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument(
        "--square",
        help="Build only this square (format: col_row). Also skips base rebuild.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel pmtiles extract workers (default: %(default)s)",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--r2-public-url",
        default=os.environ.get("R2_PUBLIC_URL", DEFAULT_R2_PUBLIC_URL),
    )
    parser.add_argument(
        "--data-dir",
        type=pathlib.Path,
        default=DATA_DIR,
        help="Where to write grid.json (default: %(default)s)",
    )
    args = parser.parse_args()

    pmtiles_bin = SCRIPT_DIR / "pmtiles"
    if not pmtiles_bin.exists():
        print(f"ERROR: {pmtiles_bin} not found. Run ./download.sh first.", file=sys.stderr)
        return 1

    missing = [str(l.source) for l in layer_specs() if not l.source.exists()]
    if missing:
        print("ERROR: master archives missing:", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        print(
            "Build or fetch them first:\n"
            "  make -f Makefile.routes download-masters\n",
            file=sys.stderr,
        )
        return 1

    grid_bbox = read_grid_bbox()
    snapshot = read_makefile_var("SNAPSHOT")
    args.out.mkdir(parents=True, exist_ok=True)

    coords = [(c, r) for c in range(args.cols) for r in range(args.rows)]
    if args.square:
        try:
            sc, sr = (int(x) for x in args.square.split("_"))
        except ValueError:
            print(f"ERROR: --square must be col_row, got {args.square!r}", file=sys.stderr)
            return 1
        coords = [(sc, sr)]

    print(
        f"Building base + {len(coords)} square(s) on {args.cols}x{args.rows} grid, "
        f"bbox={grid_bbox}, snapshot={snapshot}, out={args.out}"
    )

    base_entries: dict[str, dict] = {}
    if args.square:
        # Partial build: reuse existing base entries from prior grid.json.
        grid_json_path = args.data_dir / "grid.json"
        if grid_json_path.exists():
            try:
                base_entries = json.loads(grid_json_path.read_text()).get("base", {})
            except json.JSONDecodeError:
                base_entries = {}
        # Strip URL from reused entries; write_grid_manifest re-injects them.
        for entry in base_entries.values():
            entry.pop("url", None)
    else:
        try:
            base_entries, base_built, base_skipped = build_base(
                grid_bbox, args.out, snapshot, pmtiles_bin, args.force
            )
        except RuntimeError as exc:
            print(f"  FAIL     {exc}", file=sys.stderr)
            return 1
        print(f"Base: built={base_built} skipped={base_skipped}")

    results: dict[str, tuple[str, dict]] = {}
    counts = {"built": 0, "skipped": 0, "error": 0}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                build_square,
                col,
                row,
                args.cols,
                args.rows,
                grid_bbox,
                args.out,
                snapshot,
                pmtiles_bin,
                args.force,
            ): f"{col}_{row}"
            for col, row in coords
        }
        for future in as_completed(futures):
            square_key, status, entry = future.result()
            if status == "built":
                counts["built"] += 1
                print(f"  built    {square_key}")
            elif status == "skipped":
                counts["skipped"] += 1
                print(f"  skipped  {square_key}")
            else:
                counts["error"] += 1
                print(f"  FAIL     {square_key}: {status}", file=sys.stderr)
                continue
            results[square_key] = (status, entry)

    # Merge with any prior grid.json so --square partial builds keep other entries.
    existing_squares: dict[str, dict] = {}
    grid_json_path = args.data_dir / "grid.json"
    if grid_json_path.exists() and args.square:
        try:
            existing_squares = json.loads(grid_json_path.read_text()).get("squares", {})
        except json.JSONDecodeError:
            existing_squares = {}
    squares_out = {**existing_squares}
    for key, (_, entry) in results.items():
        squares_out[key] = entry

    manifest = {
        "version": 2,
        "source_snapshot": snapshot,
        "grid": {
            "bbox": list(grid_bbox),
            "cols": args.cols,
            "rows": args.rows,
            "pad_deg": PAD_DEG,
        },
        "layers": {
            l.name: {
                "base_minzoom": l.base_minzoom,
                "base_maxzoom": l.base_maxzoom,
                "grid_minzoom": l.grid_minzoom,
                "grid_maxzoom": l.grid_maxzoom,
            }
            for l in layer_specs()
        },
        "base": base_entries,
        "squares": squares_out,
    }
    manifest_path = write_grid_manifest(manifest, args.data_dir, args.r2_public_url)
    print(f"Wrote {manifest_path}")
    print(
        f"Done: built={counts['built']} skipped={counts['skipped']} errors={counts['error']}"
    )
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
