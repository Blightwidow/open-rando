"""Read the POI grid written by the `pois` stage."""

from __future__ import annotations

import json
from pathlib import Path

from open_rando.models import PointOfInterest
from open_rando.poi_grid import PoiGrid, Square, square_file_name

INDEX_FILE_NAME = "index.json"


class PoiGridMissingError(Exception):
    """The POI grid was never built, or was built on a different grid."""


def read_poi_squares(
    directory: Path,
    grid: PoiGrid,
    squares: list[Square],
) -> list[PointOfInterest]:
    """Every POI of the requested squares. Raises if any square was never built."""
    index_path = directory / INDEX_FILE_NAME
    if not index_path.exists():
        raise PoiGridMissingError(
            f"No POI grid at {directory}. Run `python -m open_rando pois` first."
        )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("grid") != grid.to_dict():
        raise PoiGridMissingError(
            f"POI grid at {directory} was built on a different grid {index.get('grid')}; "
            "rerun `python -m open_rando pois`."
        )

    built = {(entry["col"], entry["row"]): entry["count"] for entry in index.get("squares", [])}
    unbuilt = [square for square in squares if square not in built]
    if unbuilt:
        names = ", ".join(f"{column}_{row}" for column, row in unbuilt)
        raise PoiGridMissingError(
            f"POI squares not built: {names}. "
            "Run `python -m open_rando pois` (or `pois --square` for these)."
        )

    pois: list[PointOfInterest] = []
    for square in squares:
        if built[square] == 0:
            continue
        payload = json.loads((directory / square_file_name(square)).read_text(encoding="utf-8"))
        pois.extend(PointOfInterest.from_grid_dict(entry) for entry in payload["pois"])
    return pois
