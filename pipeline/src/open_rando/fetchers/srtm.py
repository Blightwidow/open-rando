from __future__ import annotations

import gzip
import logging
import math
import struct
from pathlib import Path

import requests

logger = logging.getLogger("open_rando")

SRTM_VOID_VALUE = -32768
SRTM1_SAMPLES = 3601
SRTM3_SAMPLES = 1201
SRTM1_FILE_SIZE = SRTM1_SAMPLES * SRTM1_SAMPLES * 2
SRTM3_FILE_SIZE = SRTM3_SAMPLES * SRTM3_SAMPLES * 2
MISSING_TILE_SENTINEL = b"MISSING"


class SrtmReader:
    """Reads elevation from cached SRTM .hgt tiles, downloading on demand."""

    def __init__(self, cache_directory: str, base_url: str) -> None:
        self.cache_directory = Path(cache_directory)
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        self._tile_cache: dict[str, bytes | None] = {}

    def get_elevation(self, latitude: float, longitude: float) -> float | None:
        """Return interpolated elevation in meters, or None if unavailable."""
        tile_name = _tile_name_for(latitude, longitude)
        tile_data = self._load_tile(tile_name)
        if tile_data is None:
            return None

        samples = _detect_samples(tile_data)
        if samples is None:
            return None

        return _bilinear_interpolate(tile_data, samples, latitude, longitude)

    def _load_tile(self, tile_name: str) -> bytes | None:
        if tile_name in self._tile_cache:
            return self._tile_cache[tile_name]

        cached_path = self.cache_directory / tile_name
        if cached_path.exists():
            data = cached_path.read_bytes()
            if data == MISSING_TILE_SENTINEL:
                self._tile_cache[tile_name] = None
                return None
            self._tile_cache[tile_name] = data
            return data

        downloaded = self._download_tile(tile_name)
        self._tile_cache[tile_name] = downloaded
        return downloaded

    def _download_tile(self, tile_name: str) -> bytes | None:
        latitude_band = tile_name[:3]
        url = f"{self.base_url}/{latitude_band}/{tile_name}.gz"
        logger.info("Downloading SRTM tile %s ...", tile_name)

        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
        except requests.RequestException as error:
            logger.warning("SRTM tile %s unavailable: %s", tile_name, error)
            cached_path = self.cache_directory / tile_name
            cached_path.write_bytes(MISSING_TILE_SENTINEL)
            return None

        decompressed = gzip.decompress(response.content)
        cached_path = self.cache_directory / tile_name
        cached_path.write_bytes(decompressed)
        logger.info("Cached SRTM tile %s (%d bytes)", tile_name, len(decompressed))
        return decompressed


def _tile_name_for(latitude: float, longitude: float) -> str:
    """Return tile filename like N45E006.hgt for the given coordinate."""
    tile_latitude = math.floor(latitude)
    tile_longitude = math.floor(longitude)

    latitude_prefix = "N" if tile_latitude >= 0 else "S"
    longitude_prefix = "E" if tile_longitude >= 0 else "W"

    return (
        f"{latitude_prefix}{abs(tile_latitude):02d}{longitude_prefix}{abs(tile_longitude):03d}.hgt"
    )


def _detect_samples(tile_data: bytes) -> int | None:
    """Detect SRTM1 (3601) or SRTM3 (1201) from file size."""
    size = len(tile_data)
    if size == SRTM1_FILE_SIZE:
        return SRTM1_SAMPLES
    if size == SRTM3_FILE_SIZE:
        return SRTM3_SAMPLES
    logger.warning("Unexpected SRTM tile size: %d bytes", size)
    return None


def _bilinear_interpolate(
    tile_data: bytes,
    samples: int,
    latitude: float,
    longitude: float,
) -> float | None:
    """Bilinear interpolation of 4 surrounding grid points."""
    tile_latitude = math.floor(latitude)
    tile_longitude = math.floor(longitude)

    fraction_row = (latitude - tile_latitude) * (samples - 1)
    fraction_column = (longitude - tile_longitude) * (samples - 1)

    row = int(fraction_row)
    column = int(fraction_column)

    row = min(row, samples - 2)
    column = min(column, samples - 2)

    delta_row = fraction_row - row
    delta_column = fraction_column - column

    # .hgt files store rows from north to south
    inverted_row = (samples - 1) - row

    elevations: list[float] = []
    for row_offset, column_offset in [(0, 0), (0, 1), (-1, 0), (-1, 1)]:
        sample_row = inverted_row + row_offset
        sample_column = column + column_offset
        byte_index = (sample_row * samples + sample_column) * 2
        value: int = struct.unpack_from(">h", tile_data, byte_index)[0]
        if value == SRTM_VOID_VALUE:
            return None
        elevations.append(float(value))

    top_left, top_right, bottom_left, bottom_right = elevations
    top = top_left + (top_right - top_left) * delta_column
    bottom = bottom_left + (bottom_right - bottom_left) * delta_column
    return top + (bottom - top) * delta_row
