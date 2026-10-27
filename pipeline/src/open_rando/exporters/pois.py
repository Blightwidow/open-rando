from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from open_rando.models import PointOfInterest
from open_rando.poi_grid import PoiGrid, Square, square_file_name

INDEX_FILE_NAME = "index.json"


def export_poi_square(
    square: Square,
    pois: Sequence[PointOfInterest],
    output_directory: str,
) -> None:
    """Write one grid square, POIs sorted by id so reruns diff cleanly."""
    column, row = square
    payload = {
        "square": {"col": column, "row": row},
        "pois": [poi.to_grid_dict() for poi in sorted(pois, key=lambda poi: poi.osm_id)],
    }
    path = Path(output_directory) / square_file_name(square)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def build_poi_index(grid: PoiGrid, counts_by_square: Mapping[Square, int]) -> dict[str, object]:
    ordered_squares = sorted(counts_by_square, key=lambda square: (square[1], square[0]))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "OpenStreetMap, SNCF open data, transport.data.gouv.fr GTFS",
        "license": "ODbL",
        "grid": grid.to_dict(),
        # Every square built so far, empty ones included: a reader must be able
        # to tell "no POI here" from "never built".
        "squares": [
            {"col": column, "row": row, "count": counts_by_square[(column, row)]}
            for column, row in ordered_squares
        ],
    }


def export_poi_index(
    grid: PoiGrid,
    counts_by_square: Mapping[Square, int],
    output_directory: str,
) -> None:
    path = Path(output_directory) / INDEX_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_poi_index(grid, counts_by_square), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def read_poi_index_counts(output_directory: str) -> dict[Square, int]:
    """Counts of squares already on disk, so a partial rerun keeps the others."""
    path = Path(output_directory) / INDEX_FILE_NAME
    if not path.exists():
        return {}
    index = json.loads(path.read_text(encoding="utf-8"))
    return {(entry["col"], entry["row"]): entry["count"] for entry in index.get("squares", [])}
