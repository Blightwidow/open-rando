from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, mapping


def export_route_geojson(
    trail: LineString | MultiLineString,
    route_id: str,
    name: str,
    output_path: str,
) -> None:
    """Export a full route trail as a GeoJSON FeatureCollection."""
    features: list[dict[str, object]] = [
        {
            "type": "Feature",
            "properties": {"id": route_id, "name": name, "feature_type": "trail"},
            "geometry": mapping(trail),
        }
    ]

    feature_collection = {"type": "FeatureCollection", "features": features}

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feature_collection, ensure_ascii=False), encoding="utf-8")
