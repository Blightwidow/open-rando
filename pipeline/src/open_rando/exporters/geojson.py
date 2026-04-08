from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import LineString, mapping


def export_geojson(
    segments: list[LineString],
    hike_id: str,
    name: str,
    output_path: str,
) -> None:
    """Export segments as a GeoJSON FeatureCollection. Each segment becomes a Feature."""
    features = [
        {
            "type": "Feature",
            "properties": {
                "id": hike_id,
                "name": name,
                "step": step_index + 1,
            },
            "geometry": mapping(segment),
        }
        for step_index, segment in enumerate(segments)
    ]

    feature_collection = {
        "type": "FeatureCollection",
        "features": features,
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feature_collection, ensure_ascii=False), encoding="utf-8")
