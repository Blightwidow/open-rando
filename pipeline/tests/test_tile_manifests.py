"""Contract tests for the tile manifests written by tiles/build-grid.py and build-routes.py.

The scripts are standalone `uv run --script` files with hyphenated names, so they are
loaded by path. CI has no master archives, so manifests are built from fixture entries
through the scripts' pure builder functions.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema
import pytest

TILES_DIRECTORY = Path(__file__).resolve().parents[2] / "tiles"
R2_PUBLIC_URL = "https://example.r2.dev"
SNAPSHOT = "20260417"
GRID_BOUNDING_BOX = (-5.5, 41.0, 10.0, 51.5)
COLUMNS = 12
ROWS = 8


def load_script(module_name: str, file_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, TILES_DIRECTORY / file_name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before executing: dataclasses resolve their module through sys.modules,
    # and the scripts' `import tile_manifests` must get this same module object so that
    # ManifestError is one class.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tiles_modules() -> Iterator[dict[str, ModuleType]]:
    module_names = ("tile_manifests", "build_grid", "build_routes")
    for module_name in module_names:
        sys.modules.pop(module_name, None)
    try:
        yield {
            "manifests": load_script("tile_manifests", "tile_manifests.py"),
            "grid": load_script("build_grid", "build-grid.py"),
            "routes": load_script("build_routes", "build-routes.py"),
        }
    finally:
        for module_name in module_names:
            sys.modules.pop(module_name, None)


def build_grid_manifest(grid_module: ModuleType, square_keys: list[str]) -> dict[str, Any]:
    layers = grid_module.layer_specs()
    base_entries = {
        layer.name: {"size": 1000, "minzoom": layer.base_minzoom, "maxzoom": layer.base_maxzoom}
        for layer in layers
    }
    squares = {
        square_key: {
            "bbox": [2.25, 47.875, 3.5, 49.0],
            "files": {
                layer.name: {
                    "size": 500,
                    "minzoom": layer.grid_minzoom,
                    "maxzoom": layer.grid_maxzoom,
                }
                for layer in layers
            },
        }
        for square_key in square_keys
    }
    manifest = grid_module.build_manifest(
        SNAPSHOT, GRID_BOUNDING_BOX, COLUMNS, ROWS, base_entries, squares
    )
    return grid_module.with_urls(manifest, R2_PUBLIC_URL)  # type: ignore[no-any-return]


def build_route_manifest(
    routes_module: ModuleType, squares: list[list[int]], snapshot: str = SNAPSHOT
) -> dict[str, Any]:
    return routes_module.build_route_manifest(  # type: ignore[no-any-return]
        "0fbbaf4616b4", snapshot, [1.7, 48.3, 2.9, 49.2], squares
    )


@pytest.mark.parametrize("schema_name", ["tile-grid.schema.json", "route-tiles.schema.json"])
def test_schema_is_valid_json_schema(
    tiles_modules: dict[str, ModuleType], schema_name: str
) -> None:
    schema = tiles_modules["manifests"].load_schema(schema_name)

    jsonschema.Draft202012Validator.check_schema(schema)


def test_grid_manifest_from_builder_is_valid(tiles_modules: dict[str, ModuleType]) -> None:
    manifest = build_grid_manifest(tiles_modules["grid"], ["5_5", "6_5"])

    tiles_modules["manifests"].validate_grid_manifest(manifest)


def test_grid_manifest_survives_json_round_trip(tiles_modules: dict[str, ModuleType]) -> None:
    manifest = build_grid_manifest(tiles_modules["grid"], ["6_5"])

    tiles_modules["manifests"].validate_grid_manifest(json.loads(json.dumps(manifest)))


def test_grid_manifest_accepts_an_extra_layer(tiles_modules: dict[str, ModuleType]) -> None:
    manifest = build_grid_manifest(tiles_modules["grid"], ["6_5"])
    manifest["layers"]["overlay"] = {
        "base_minzoom": 6,
        "base_maxzoom": 10,
        "grid_minzoom": 11,
        "grid_maxzoom": 13,
    }
    manifest["base"]["overlay"] = {
        "url": f"{R2_PUBLIC_URL}/base/overlay.pmtiles",
        "size": 1,
        "minzoom": 6,
        "maxzoom": 10,
    }
    manifest["squares"]["6_5"]["files"]["overlay"] = {
        "url": f"{R2_PUBLIC_URL}/grid/6_5/overlay.pmtiles",
        "size": 1,
        "minzoom": 11,
        "maxzoom": 13,
    }

    tiles_modules["manifests"].validate_grid_manifest(manifest)


def test_grid_manifest_rejects_a_snapshot_that_is_not_a_date(
    tiles_modules: dict[str, ModuleType],
) -> None:
    manifest = build_grid_manifest(tiles_modules["grid"], ["6_5"])
    manifest["source_snapshot"] = "latest"

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="source_snapshot"):
        tiles_modules["manifests"].validate_grid_manifest(manifest)


def test_grid_manifest_rejects_a_file_without_url(tiles_modules: dict[str, ModuleType]) -> None:
    manifest = build_grid_manifest(tiles_modules["grid"], ["6_5"])
    del manifest["squares"]["6_5"]["files"]["contours"]["url"]

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="url"):
        tiles_modules["manifests"].validate_grid_manifest(manifest)


def test_grid_manifest_rejects_a_missing_base_layer(
    tiles_modules: dict[str, ModuleType],
) -> None:
    manifest = build_grid_manifest(tiles_modules["grid"], ["6_5"])
    del manifest["base"]["hillshade"]

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="base layers"):
        tiles_modules["manifests"].validate_grid_manifest(manifest)


def test_grid_manifest_rejects_a_square_missing_a_layer(
    tiles_modules: dict[str, ModuleType],
) -> None:
    manifest = build_grid_manifest(tiles_modules["grid"], ["6_5"])
    del manifest["squares"]["6_5"]["files"]["hillshade"]

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="square 6_5 layers"):
        tiles_modules["manifests"].validate_grid_manifest(manifest)


def test_grid_manifest_rejects_a_square_zoom_range_that_drifted_from_layers(
    tiles_modules: dict[str, ModuleType],
) -> None:
    manifest = build_grid_manifest(tiles_modules["grid"], ["6_5"])
    manifest["squares"]["6_5"]["files"]["contours"]["maxzoom"] = 14

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="zoom range"):
        tiles_modules["manifests"].validate_grid_manifest(manifest)


def test_grid_manifest_rejects_a_square_outside_the_grid(
    tiles_modules: dict[str, ModuleType],
) -> None:
    manifest = build_grid_manifest(tiles_modules["grid"], ["12_0"])

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="outside the 12x8 grid"):
        tiles_modules["manifests"].validate_grid_manifest(manifest)


def test_write_grid_manifest_writes_nothing_when_invalid(
    tiles_modules: dict[str, ModuleType], tmp_path: Path
) -> None:
    grid_module = tiles_modules["grid"]
    manifest = build_grid_manifest(grid_module, ["6_5"])
    del manifest["base"]["hillshade"]

    with pytest.raises(tiles_modules["manifests"].ManifestError):
        grid_module.write_grid_manifest(manifest, tmp_path, R2_PUBLIC_URL)

    assert not (tmp_path / "grid.json").exists()


def test_write_grid_manifest_stamps_urls_into_the_written_file(
    tiles_modules: dict[str, ModuleType], tmp_path: Path
) -> None:
    grid_module = tiles_modules["grid"]
    unstamped = build_grid_manifest(grid_module, ["6_5"])
    for entry in unstamped["base"].values():
        entry.pop("url")
    for square in unstamped["squares"].values():
        for entry in square["files"].values():
            entry.pop("url")

    path = grid_module.write_grid_manifest(unstamped, tmp_path, R2_PUBLIC_URL)

    written = json.loads(path.read_text())
    assert written["squares"]["6_5"]["files"]["contours"]["url"] == (
        f"{R2_PUBLIC_URL}/grid/6_5/contours.pmtiles"
    )


def test_route_manifest_without_grid_is_checked_for_shape_only(
    tiles_modules: dict[str, ModuleType],
) -> None:
    manifest = build_route_manifest(tiles_modules["routes"], [[5, 5], [6, 5]])

    tiles_modules["manifests"].validate_route_manifest(manifest)


def test_route_manifest_from_real_square_computation_is_valid_against_grid(
    tiles_modules: dict[str, ModuleType],
) -> None:
    routes_module = tiles_modules["routes"]
    route_bbox = [1.7160437, 48.2921791, 2.9390362, 49.1628759]
    squares = routes_module.route_squares(route_bbox, COLUMNS, ROWS, GRID_BOUNDING_BOX)
    grid_manifest = build_grid_manifest(
        tiles_modules["grid"], [f"{col}_{row}" for col, row in squares]
    )
    manifest = routes_module.build_route_manifest("0fbbaf4616b4", SNAPSHOT, route_bbox, squares)

    tiles_modules["manifests"].validate_route_manifest(manifest, grid_manifest)


def test_route_manifest_rejects_a_square_missing_from_the_grid(
    tiles_modules: dict[str, ModuleType],
) -> None:
    grid_manifest = build_grid_manifest(tiles_modules["grid"], ["5_5"])
    manifest = build_route_manifest(tiles_modules["routes"], [[5, 5], [6, 5]])

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="6_5 is not in grid.json"):
        tiles_modules["manifests"].validate_route_manifest(manifest, grid_manifest)


def test_route_manifest_rejects_a_snapshot_that_differs_from_the_grid(
    tiles_modules: dict[str, ModuleType],
) -> None:
    grid_manifest = build_grid_manifest(tiles_modules["grid"], ["5_5"])
    manifest = build_route_manifest(tiles_modules["routes"], [[5, 5]], snapshot="20250101")

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="differs from grid.json"):
        tiles_modules["manifests"].validate_route_manifest(manifest, grid_manifest)


def test_route_manifest_rejects_a_duplicated_square(
    tiles_modules: dict[str, ModuleType],
) -> None:
    grid_manifest = build_grid_manifest(tiles_modules["grid"], ["5_5"])
    manifest = build_route_manifest(tiles_modules["routes"], [[5, 5], [5, 5]])

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="listed twice"):
        tiles_modules["manifests"].validate_route_manifest(manifest, grid_manifest)


def test_route_manifest_rejects_a_square_that_is_not_a_pair(
    tiles_modules: dict[str, ModuleType],
) -> None:
    manifest = build_route_manifest(tiles_modules["routes"], [[5, 5, 5]])

    with pytest.raises(tiles_modules["manifests"].ManifestError, match="squares"):
        tiles_modules["manifests"].validate_route_manifest(manifest)


def test_builders_do_not_mutate_their_inputs(tiles_modules: dict[str, ModuleType]) -> None:
    grid_module = tiles_modules["grid"]
    manifest = grid_module.build_manifest(SNAPSHOT, GRID_BOUNDING_BOX, COLUMNS, ROWS, {}, {})
    before = copy.deepcopy(manifest)

    grid_module.with_urls(manifest, R2_PUBLIC_URL)

    assert manifest == before
