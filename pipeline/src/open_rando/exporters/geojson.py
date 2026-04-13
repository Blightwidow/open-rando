from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, mapping

from open_rando.models import PointOfInterest


def export_route_geojson(
    trail: LineString | MultiLineString,
    route_id: str,
    name: str,
    pois: list[PointOfInterest],
    output_path: str,
) -> None:
    """Export a full route trail and its POIs as a GeoJSON FeatureCollection."""
    features: list[dict[str, object]] = [
        {
            "type": "Feature",
            "properties": {"id": route_id, "name": name, "feature_type": "trail"},
            "geometry": mapping(trail),
        }
    ]

    for poi in pois:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "feature_type": "poi",
                    "poi_type": poi.poi_type,
                    "name": poi.name,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [poi.lon, poi.lat],
                },
            }
        )

    feature_collection = {"type": "FeatureCollection", "features": features}

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feature_collection, ensure_ascii=False), encoding="utf-8")
