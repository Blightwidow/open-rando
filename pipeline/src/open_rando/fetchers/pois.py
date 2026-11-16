from __future__ import annotations

import logging

from open_rando.models import PointOfInterest
from open_rando.osm_tags import ACCOMMODATION_KINDS, RESUPPLY_EATERY_KINDS, RESUPPLY_SHOP_KINDS

logger = logging.getLogger("open_rando")

BOUNDING_BOX_MARGIN_DEGREES = 0.03  # ~3km matches search radius
POI_ACCOMMODATION_RADIUS_METERS = 3000
POI_RESUPPLY_RADIUS_METERS = 1500


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


def _parse_resupply_elements(
    data: dict,  # type: ignore[type-arg]
) -> list[PointOfInterest]:
    """Parse OSM elements into food shop and eatery POIs.

    Unnamed ones are dropped, and so is a place also tagged as lodging (a hotel with a
    restaurant): the accommodation layer already holds it under the same OSM id, and a
    grid square keeps one record per id.
    """
    pois: list[PointOfInterest] = []

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name", "")
        if not name:
            continue

        if tags.get("tourism", "") in ACCOMMODATION_KINDS:
            continue

        shop = tags.get("shop", "")
        amenity = tags.get("amenity", "")
        if shop in RESUPPLY_SHOP_KINDS:
            poi_type, category = "shop", shop
        elif amenity in RESUPPLY_EATERY_KINDS:
            poi_type, category = "eatery", amenity
        else:
            continue

        if "lat" in element and "lon" in element:
            lat = element["lat"]
            lon = element["lon"]
        elif "center" in element:
            lat = element["center"]["lat"]
            lon = element["center"]["lon"]
        else:
            continue

        pois.append(
            PointOfInterest(
                name=name,
                lat=lat,
                lon=lon,
                poi_type=poi_type,
                url=tags.get("website") or tags.get("contact:website") or None,
                category=category,
                opening_hours=tags.get("opening_hours") or None,
                phone=tags.get("phone") or tags.get("contact:phone") or None,
                osm_id=f"{element.get('type', 'node')}/{element.get('id', '')}",
            )
        )

    return pois
