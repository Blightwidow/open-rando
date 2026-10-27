"""Fixed grid that splits France-wide POIs into files.

The grid matches `tiles/build-grid.py` (same bbox, same 12x8 squares), so a
client that already knows which map squares it downloaded knows which POI
squares to load.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

GRID_BOUNDING_BOX = (-5.5, 41.0, 10.0, 51.5)  # lon_min, lat_min, lon_max, lat_max
GRID_COLUMNS = 12
GRID_ROWS = 8

Square = tuple[int, int]


@dataclass(frozen=True)
class PoiGrid:
    bounding_box: tuple[float, float, float, float] = GRID_BOUNDING_BOX
    columns: int = GRID_COLUMNS
    rows: int = GRID_ROWS

    @property
    def longitude_step(self) -> float:
        return (self.bounding_box[2] - self.bounding_box[0]) / self.columns

    @property
    def latitude_step(self) -> float:
        return (self.bounding_box[3] - self.bounding_box[1]) / self.rows

    def contains(self, lat: float, lon: float) -> bool:
        lon_min, lat_min, lon_max, lat_max = self.bounding_box
        return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max

    def square_for_point(self, lat: float, lon: float) -> Square | None:
        """Square holding the point, or None when it lies outside the grid.

        A point on the outer east or north edge belongs to the last square.
        """
        if not self.contains(lat, lon):
            return None
        lon_min, lat_min, _, _ = self.bounding_box
        column = min(int((lon - lon_min) / self.longitude_step), self.columns - 1)
        row = min(int((lat - lat_min) / self.latitude_step), self.rows - 1)
        return column, row

    def squares_for_bounding_box(
        self,
        bounding_box: tuple[float, float, float, float],
        margin_degrees: float = 0.0,
    ) -> list[Square]:
        """Squares intersecting (lon_min, lat_min, lon_max, lat_max) plus a margin."""
        grid_lon_min, grid_lat_min, grid_lon_max, grid_lat_max = self.bounding_box
        lon_min = max(bounding_box[0] - margin_degrees, grid_lon_min)
        lat_min = max(bounding_box[1] - margin_degrees, grid_lat_min)
        lon_max = min(bounding_box[2] + margin_degrees, grid_lon_max)
        lat_max = min(bounding_box[3] + margin_degrees, grid_lat_max)
        if lon_min > lon_max or lat_min > lat_max:
            return []

        first_column = int(math.floor((lon_min - grid_lon_min) / self.longitude_step))
        last_column = int(math.floor((lon_max - grid_lon_min) / self.longitude_step))
        first_row = int(math.floor((lat_min - grid_lat_min) / self.latitude_step))
        last_row = int(math.floor((lat_max - grid_lat_min) / self.latitude_step))
        return [
            (column, row)
            for row in range(max(first_row, 0), min(last_row, self.rows - 1) + 1)
            for column in range(max(first_column, 0), min(last_column, self.columns - 1) + 1)
        ]

    def square_bounding_box(self, square: Square) -> tuple[float, float, float, float]:
        column, row = square
        lon_min, lat_min, _, _ = self.bounding_box
        return (
            lon_min + column * self.longitude_step,
            lat_min + row * self.latitude_step,
            lon_min + (column + 1) * self.longitude_step,
            lat_min + (row + 1) * self.latitude_step,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "bbox": list(self.bounding_box),
            "cols": self.columns,
            "rows": self.rows,
        }


def square_file_name(square: Square) -> str:
    column, row = square
    return f"{column}_{row}.json"
