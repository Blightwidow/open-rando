from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("open_rando")

ROUTES_YAML_PATH = Path(__file__).resolve().parents[3] / "routes.yaml"


def discover_routes(
    routes_path: Path = ROUTES_YAML_PATH,
) -> list[dict[str, Any]]:
    """Load GR routes from routes.yaml.

    Only routes with a relation_id are returned — routes without one
    are not yet mapped in OSM and cannot be processed.

    Returns a sorted list of route dicts.
    Each entry has: relation_id, relation_ids, ref, name.
    """
    raw = yaml.safe_load(routes_path.read_text(encoding="utf-8"))
    entries = raw.get("routes", [])

    routes: list[dict[str, Any]] = []
    skipped_count = 0
    for entry in entries:
        relation_id = entry.get("relation_id")
        if relation_id is None:
            skipped_count += 1
            continue
        routes.append({
            "relation_id": relation_id,
            "relation_ids": [relation_id],
            "ref": entry["ref"],
            "name": entry.get("name", ""),
            "description": entry.get("description", ""),
        })

    routes.sort(key=lambda route: str(route["ref"]))

    logger.info(
        "Loaded %d routes from %s (%d skipped, no relation_id)",
        len(routes),
        routes_path.name,
        skipped_count,
    )

    return routes
