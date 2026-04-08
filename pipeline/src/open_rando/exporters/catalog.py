from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from open_rando.models import Hike


def export_catalog(hikes: list[Hike], output_path: str) -> None:
    """Write catalog.json containing all hike metadata."""
    catalog = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL",
        "hikes": [hike.to_dict() for hike in hikes],
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
