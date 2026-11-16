"""Contract checks for the tile manifests the mobile client reads.

`grid.json` (written by build-grid.py) and `routes/{id}/pmtiles.json`
(written by build-routes.py) are validated against the JSON Schemas in
pipeline/src/open_rando/data/, plus the cross-checks a schema cannot express.
A shape change must fail the build instead of shipping silently.

Needs `jsonschema`; the build scripts declare it in their inline deps.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import jsonschema

SCHEMA_DIR = pathlib.Path(__file__).resolve().parent.parent / "pipeline/src/open_rando/data"
GRID_SCHEMA = "tile-grid.schema.json"
ROUTE_SCHEMA = "route-tiles.schema.json"
MAX_REPORTED_ERRORS = 5


class ManifestError(Exception):
    """Raised when a manifest does not match its contract."""


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def check_schema(document: dict[str, Any], schema_name: str) -> None:
    validator = jsonschema.Draft202012Validator(load_schema(schema_name))
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if not errors:
        return
    reported = errors[:MAX_REPORTED_ERRORS]
    details = "\n".join(
        f"  {'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in reported
    )
    suffix = (
        "" if len(errors) == len(reported) else f"\n  ... and {len(errors) - len(reported)} more"
    )
    raise ManifestError(
        f"manifest does not match {schema_name} ({len(errors)} error(s)):\n{details}{suffix}"
    )


def validate_grid_manifest(manifest: dict[str, Any]) -> None:
    """Schema check, then layer, zoom and square-key consistency."""
    check_schema(manifest, GRID_SCHEMA)

    problems: list[str] = []
    layers: dict[str, dict[str, int]] = manifest["layers"]
    layer_names = set(layers)

    base: dict[str, dict[str, Any]] = manifest["base"]
    if set(base) != layer_names:
        problems.append(
            f"base layers {sorted(base)} differ from layers {sorted(layer_names)}"
            " (partial --square build without a prior full grid.json?)"
        )
    for layer_name, entry in base.items():
        spec = layers.get(layer_name)
        if spec and (entry["minzoom"], entry["maxzoom"]) != (
            spec["base_minzoom"],
            spec["base_maxzoom"],
        ):
            problems.append(f"base/{layer_name} zoom range does not match layers.{layer_name}")

    cols = manifest["grid"]["cols"]
    rows = manifest["grid"]["rows"]
    for square_key, square in manifest["squares"].items():
        col, row = (int(part) for part in square_key.split("_"))
        if col >= cols or row >= rows:
            problems.append(f"square {square_key} is outside the {cols}x{rows} grid")
        files: dict[str, dict[str, Any]] = square["files"]
        if set(files) != layer_names:
            problems.append(
                f"square {square_key} layers {sorted(files)} differ from layers "
                f"{sorted(layer_names)}"
            )
        for layer_name, entry in files.items():
            spec = layers.get(layer_name)
            if spec and (entry["minzoom"], entry["maxzoom"]) != (
                spec["grid_minzoom"],
                spec["grid_maxzoom"],
            ):
                problems.append(
                    f"square {square_key}/{layer_name} zoom range does not match "
                    f"layers.{layer_name}"
                )

    if problems:
        raise ManifestError("grid manifest is inconsistent:\n  " + "\n  ".join(problems))


def validate_route_manifest(
    manifest: dict[str, Any],
    grid_manifest: dict[str, Any] | None = None,
) -> None:
    """Schema check, then (when the grid is known) square and snapshot consistency."""
    check_schema(manifest, ROUTE_SCHEMA)
    if grid_manifest is None:
        return

    problems: list[str] = []
    if manifest["source_snapshot"] != grid_manifest["source_snapshot"]:
        problems.append(
            f"source_snapshot {manifest['source_snapshot']} differs from grid.json "
            f"{grid_manifest['source_snapshot']}"
        )
    seen: set[tuple[int, int]] = set()
    for col, row in manifest["squares"]:
        if (col, row) in seen:
            problems.append(f"square {col}_{row} listed twice")
        seen.add((col, row))
        if f"{col}_{row}" not in grid_manifest["squares"]:
            problems.append(f"square {col}_{row} is not in grid.json")

    if problems:
        raise ManifestError(
            f"route manifest {manifest['route_id']} is inconsistent:\n  " + "\n  ".join(problems)
        )
