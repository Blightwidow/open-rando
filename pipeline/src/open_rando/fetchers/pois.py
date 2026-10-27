from __future__ import annotations

import logging

from open_rando.models import PointOfInterest

logger = logging.getLogger("open_rando")

BOUNDING_BOX_MARGIN_DEGREES = 0.03  # ~3km matches search radius
POI_ACCOMMODATION_RADIUS_METERS = 3000


def _parse_accommodation_elements(
    data: dict,  # type: ignore[type-arg]
) -> list[PointOfInterest]:
    """Parse Overpass response into accommodation POIs."""
    pois: list[PointOfInterest] = []

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        tourism = tags.get("tourism", "")

        name = tags.get("name", "")
        if not name:
            continue

        # Get coordinates (nodes have lat/lon, ways have center)
        if "lat" in element and "lon" in element:
            lat = element["lat"]
            lon = element["lon"]
        elif "center" in element:
            lat = element["center"]["lat"]
            lon = element["center"]["lon"]
        else:
            continue

        poi_type = "camping" if tourism == "camp_site" else "hotel"
        url = tags.get("website") or tags.get("contact:website") or None

        pois.append(
            PointOfInterest(
                name=name,
                lat=lat,
                lon=lon,
                poi_type=poi_type,
                url=url,
                osm_id=f"{element.get('type', 'node')}/{element.get('id', '')}",
            )
        )

    return pois
