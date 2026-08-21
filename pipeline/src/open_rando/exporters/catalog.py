from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

from open_rando.models import Route

SCHEMA_RESOURCE = "catalog.schema.json"
MAX_REPORTED_ERRORS = 5


class CatalogValidationError(Exception):
    """Raised when the catalog does not match the published contract."""


def load_catalog_schema() -> dict[str, Any]:
    """Load the JSON Schema describing catalog.json."""
    schema_text = (
        resources.files("open_rando.data").joinpath(SCHEMA_RESOURCE).read_text(encoding="utf-8")
    )
    return json.loads(schema_text)  # type: ignore[no-any-return]


def validate_catalog(catalog: dict[str, Any]) -> None:
    """Validate a catalog against the schema, reporting every mismatch found.

    The website and the mobile client both read catalog.json, so a shape change
    must fail the pipeline instead of shipping silently.
    """
    validator = jsonschema.Draft202012Validator(load_catalog_schema())
    errors = sorted(validator.iter_errors(catalog), key=lambda error: list(error.absolute_path))
    if not errors:
        return

    reported = errors[:MAX_REPORTED_ERRORS]
    details = "\n".join(
        f"  {'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in reported
    )
    suffix = (
        "" if len(errors) == len(reported) else f"\n  ... and {len(errors) - len(reported)} more"
    )
    raise CatalogValidationError(
        f"catalog.json does not match {SCHEMA_RESOURCE} "
        f"({len(errors)} error(s)):\n{details}{suffix}"
    )


def build_catalog(routes: Sequence[Route | dict[str, Any]]) -> dict[str, Any]:
    """Assemble the catalog payload written to catalog.json."""
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL",
        "routes": [route.to_dict() if isinstance(route, Route) else route for route in routes],
    }


def export_route_catalog(routes: Sequence[Route | dict[str, Any]], output_path: str) -> None:
    """Write catalog.json containing all route metadata with ordered stations."""
    catalog = build_catalog(routes)
    validate_catalog(catalog)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
