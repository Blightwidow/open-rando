from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from open_rando.exporters.catalog import LINKS_SCHEMA_RESOURCE, validate_document
from open_rando.models import PoiLink


def export_links(
    route_id: str,
    links: Sequence[PoiLink],
    counts: Mapping[str, int],
    output_directory: Path,
) -> None:
    """Write links/<route_id>.json, validated against the links schema."""
    payload: dict[str, Any] = {
        "route_id": route_id,
        "counts": dict(counts),
        "links": [link.to_dict() for link in links],
    }
    validate_document(payload, LINKS_SCHEMA_RESOURCE)
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / f"{route_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _read(route_id: str, output_directory: Path) -> dict[str, Any]:
    return json.loads((output_directory / f"{route_id}.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def load_links(route_id: str, output_directory: Path) -> list[PoiLink]:
    return [PoiLink.from_dict(entry) for entry in _read(route_id, output_directory)["links"]]


def load_link_counts(route_id: str, output_directory: Path) -> dict[str, int]:
    return dict(_read(route_id, output_directory)["counts"])
