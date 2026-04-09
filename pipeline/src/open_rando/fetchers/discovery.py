from __future__ import annotations

import logging
import time
from typing import Any

from open_rando.config import DISCOVERY_CACHE_TTL_SECONDS, OVERPASS_COOLDOWN_SECONDS
from open_rando.fetchers.overpass import query_overpass
from open_rando.models import determine_route_type

logger = logging.getLogger("open_rando")

GR_DISCOVERY_QUERY = """
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

PR_DISCOVERY_QUERY = """
[out:json][timeout:180];
area["ISO3166-1"="FR"]->.france;
(
  rel["route"="hiking"]["ref"~"^PR"](area.france);
);
out body;
(
  rel["route"="hiking"](area.france);
);
<<;
rel._["type"="superroute"]["ref"~"^PR"];
out body;
"""


def _parse_discovery_response(
    elements: list[dict[str, Any]],
) -> list[dict[str, str | int]]:
    """Parse Overpass response elements into route dicts."""
    relations: dict[int, dict[str, str | int]] = {}
    child_relation_ids: set[int] = set()

    for element in elements:
        if element.get("type") != "relation":
            continue

        relation_id = element["id"]
        tags = element.get("tags", {})
        ref = tags.get("ref", "")
        name = tags.get("name", "")
        relation_type = tags.get("type", "")

        if not ref:
            continue

        relations[relation_id] = {
            "relation_id": relation_id,
            "ref": ref,
            "name": name,
            "route_type": determine_route_type(ref),
        }

        if relation_type == "superroute":
            for member in element.get("members", []):
                if member.get("type") == "relation":
                    child_relation_ids.add(member["ref"])

    top_level = [
        route for relation_id, route in relations.items() if relation_id not in child_relation_ids
    ]

    return top_level


def discover_routes(
    route_types: list[str] | None = None,
) -> list[dict[str, str | int]]:
    """Discover hiking routes in France via Overpass.

    Args:
        route_types: Filter by route type(s). None means all types.
            Valid values: "gr", "grp", "pr".
            "gr" includes both GR and GRP routes in the query.

    Returns a sorted list of top-level routes.
    Each entry: {"relation_id": int, "ref": str, "name": str, "route_type": str}.
    """
    all_routes: dict[int, dict[str, str | int]] = {}

    include_gr = route_types is None or any(
        route_type in ("gr", "grp") for route_type in route_types
    )
    include_pr = route_types is None or "pr" in route_types

    if include_gr:
        data, _cache_hit = query_overpass(
            GR_DISCOVERY_QUERY, cache_ttl_seconds=DISCOVERY_CACHE_TTL_SECONDS
        )
        for route in _parse_discovery_response(data.get("elements", [])):
            all_routes[int(route["relation_id"])] = route

        logger.info("Discovered %d GR/GRP routes", len(all_routes))

    if include_pr:
        if include_gr:
            time.sleep(OVERPASS_COOLDOWN_SECONDS)

        data, _cache_hit = query_overpass(
            PR_DISCOVERY_QUERY, cache_ttl_seconds=DISCOVERY_CACHE_TTL_SECONDS
        )
        pr_routes = _parse_discovery_response(data.get("elements", []))
        pr_count = 0
        for route in pr_routes:
            relation_id = int(route["relation_id"])
            if relation_id not in all_routes:
                all_routes[relation_id] = route
                pr_count += 1

        logger.info("Discovered %d PR routes", pr_count)

    top_level = list(all_routes.values())

    # Filter by requested route types
    if route_types is not None:
        top_level = [route for route in top_level if route["route_type"] in route_types]

    top_level.sort(key=lambda route: str(route["ref"]))

    logger.info("Total: %d routes to process", len(top_level))

    return top_level
