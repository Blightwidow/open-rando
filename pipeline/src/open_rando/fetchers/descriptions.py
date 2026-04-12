from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

import yaml


@dataclass
class RouteDescription:
    ref: str
    tagline: str
    description: str


def load_route_descriptions() -> dict[str, RouteDescription]:
    """Load GR route descriptions from the bundled YAML data file."""
    data_file = files("open_rando.data").joinpath("gr-descriptions.yaml")
    raw: dict[str, dict[str, dict[str, str]]] = yaml.safe_load(
        data_file.read_text(encoding="utf-8")
    )
    routes = raw.get("routes") or {}
    return {
        ref: RouteDescription(ref=ref, tagline=entry["tagline"], description=entry["description"])
        for ref, entry in routes.items()
    }
