#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["rasterio>=1.3", "mercantile>=1.2", "numpy>=1.26", "pillow>=10"]
# ///
"""Encode a DEM GeoTIFF (EPSG:3857) to Mapbox-RGB PNG tiles in an MBTiles.

Mapbox RGB encoding: height = -10000 + (R*65536 + G*256 + B) * 0.1
MapLibre consumes this via `"type": "raster-dem", "encoding": "mapbox"`.
"""

import argparse
import sqlite3
from io import BytesIO
from pathlib import Path

import mercantile
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds


def encode_mapbox_rgb(elevation: np.ndarray) -> np.ndarray:
    value = ((elevation.astype(np.float64) + 10000.0) / 0.1).round().astype(np.int64)
    value = np.clip(value, 0, (1 << 24) - 1)
    red_channel = ((value >> 16) & 0xFF).astype(np.uint8)
    green_channel = ((value >> 8) & 0xFF).astype(np.uint8)
    blue_channel = (value & 0xFF).astype(np.uint8)
    return np.stack([red_channel, green_channel, blue_channel], axis=-1)


def init_mbtiles(db_path: Path, name: str, min_zoom: int, max_zoom: int, bounds: tuple[float, float, float, float]) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE metadata (name TEXT, value TEXT);
        CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);
        CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);
        """
    )
    metadata = {
        "name": name,
        "format": "png",
        "type": "baselayer",
        "version": "1",
        "description": "Mapbox RGB DEM",
        "minzoom": str(min_zoom),
        "maxzoom": str(max_zoom),
        "bounds": ",".join(str(coordinate) for coordinate in bounds),
    }
    for key, value in metadata.items():
        connection.execute("INSERT INTO metadata VALUES (?, ?)", (key, value))
    connection.commit()
    return connection


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dem")
    parser.add_argument("output_mbtiles")
    parser.add_argument("--min-z", type=int, default=5)
    parser.add_argument("--max-z", type=int, default=11)
    parser.add_argument("--tile-size", type=int, default=512)
    args = parser.parse_args()

    output_path = Path(args.output_mbtiles)
    if output_path.exists():
        output_path.unlink()

    with rasterio.open(args.input_dem) as source:
        geographic_bounds = transform_bounds(
            source.crs, "EPSG:4326", *source.bounds, densify_pts=21
        )
        connection = init_mbtiles(
            output_path, output_path.stem, args.min_z, args.max_z, geographic_bounds
        )

        for zoom in range(args.min_z, args.max_z + 1):
            tiles = list(mercantile.tiles(*geographic_bounds, zoom))
            print(f"z{zoom}: {len(tiles)} tiles")
            for index, tile in enumerate(tiles):
                if index % 200 == 0 and index > 0:
                    print(f"  {index}/{len(tiles)}")
                mercator_bounds = mercantile.xy_bounds(tile)
                window = from_bounds(
                    mercator_bounds.left,
                    mercator_bounds.bottom,
                    mercator_bounds.right,
                    mercator_bounds.top,
                    transform=source.transform,
                )
                elevation_data = source.read(
                    1,
                    window=window,
                    out_shape=(args.tile_size, args.tile_size),
                    resampling=Resampling.bilinear,
                    boundless=True,
                    fill_value=0,
                )
                rgb = encode_mapbox_rgb(elevation_data)
                image = Image.fromarray(rgb, "RGB")
                buffer = BytesIO()
                image.save(buffer, "PNG", optimize=True)
                tms_row = (1 << zoom) - 1 - tile.y
                connection.execute(
                    "INSERT INTO tiles VALUES (?, ?, ?, ?)",
                    (zoom, tile.x, tms_row, buffer.getvalue()),
                )
            connection.commit()

    connection.close()
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
