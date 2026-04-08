from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import LineString, mapping


def export_geojson(
    segment: LineString,
    hike_id: str,
    name: str,
    output_path: str,
) -> None:
    """Export a segment as a GeoJSON FeatureCollection."""
    feature = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": hike_id,
                    "name": name,
                },
                "geometry": mapping(segment),
            }
        ],
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feature, ensure_ascii=False), encoding="utf-8")
