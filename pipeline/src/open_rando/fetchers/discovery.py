from __future__ import annotations

import logging

from open_rando.config import DISCOVERY_CACHE_TTL_SECONDS
from open_rando.fetchers.overpass import query_overpass

logger = logging.getLogger("open_rando")


def discover_gr_routes() -> list[dict[str, str | int | bool]]:
    """Discover all GR/GRP hiking routes in France via Overpass.

    Uses two query stages:
    1. Find hiking routes with ref~^GR within France (catches routes with ref tags)
    2. Find ALL hiking routes in France, recurse up to parent superroutes,
       then filter for ref~^GR (catches superroutes whose children lack ref tags)

    Returns a sorted list of top-level routes (superroutes preferred over children).
    Each entry: {"relation_id": int, "ref": str, "name": str, "is_grp": bool}.
    """
    query = """
[out:json][timeout:180];
area["ISO3166-1"="FR"]->.france;
(
  rel["route"="hiking"]["ref"~"^GR"](area.france);
);
out body;
(
  rel["route"="hiking"](area.france);
);
<<;
rel._["type"="superroute"]["ref"~"^GR"];
out body;
"""
    data = query_overpass(query, cache_ttl_seconds=DISCOVERY_CACHE_TTL_SECONDS)
    elements = data.get("elements", [])

    # Collect all relations with ref tags and identify superroute children
    relations: dict[int, dict[str, str | int | bool]] = {}
    child_relation_ids: set[int] = set()

    for element in elements:
        if element.get("type") != "relation":
            continue

        relation_id = element["id"]
        tags = element.get("tags", {})
        ref = tags.get("ref", "")
        name = tags.get("name", "")
        route_type = tags.get("type", "")

        if not ref:
            continue

        is_grp = "GRP" in ref.upper() or "PAYS" in ref.upper()

        relations[relation_id] = {
            "relation_id": relation_id,
            "ref": ref,
            "name": name,
            "is_grp": is_grp,
        }

        # If this is a superroute, mark its child relations for exclusion
        if route_type == "superroute":
            for member in element.get("members", []):
                if member.get("type") == "relation":
                    child_relation_ids.add(member["ref"])

    # Filter out children of superroutes (they'll be fetched via their parent)
    top_level = [
        route for relation_id, route in relations.items() if relation_id not in child_relation_ids
    ]

    top_level.sort(key=lambda route: str(route["ref"]))

    logger.info(
        "Discovered %d top-level GR routes (%d total relations, %d children excluded)",
        len(top_level),
        len(relations),
        len(child_relation_ids),
    )

    return top_level
