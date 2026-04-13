from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_rando.models import Route


def export_route_catalog(
    routes: list[Route | dict[str, Any]], output_path: str
) -> None:
    """Write catalog.json containing all route metadata with ordered stations."""
    catalog = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL",
        "routes": [
            route.to_dict() if isinstance(route, Route) else route
            for route in routes
        ],
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
