from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

CATALOG_SCHEMA_RESOURCE = "catalog.schema.json"
POI_SQUARE_SCHEMA_RESOURCE = "poi-square.schema.json"
POI_INDEX_SCHEMA_RESOURCE = "poi-index.schema.json"
LINKS_SCHEMA_RESOURCE = "links.schema.json"
MAX_REPORTED_ERRORS = 5


class CatalogValidationError(Exception):
    """Raised when a published file does not match its contract."""


def load_schema(resource: str) -> dict[str, Any]:
    """Load one of the JSON Schemas shipped with the package."""
    schema_text = resources.files("open_rando.data").joinpath(resource).read_text(encoding="utf-8")
    return json.loads(schema_text)  # type: ignore[no-any-return]


def load_catalog_schema() -> dict[str, Any]:
    """Load the JSON Schema describing catalog.json."""
    return load_schema(CATALOG_SCHEMA_RESOURCE)


def validate_document(document: dict[str, Any], schema_resource: str) -> None:
    """Validate a document against a schema, reporting every mismatch found.

    The website and the mobile client read these files, so a shape change must
    fail the pipeline instead of shipping silently.
    """
    validator = jsonschema.Draft202012Validator(load_schema(schema_resource))
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
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
        f"document does not match {schema_resource} ({len(errors)} error(s)):\n{details}{suffix}"
    )


def validate_catalog(catalog: dict[str, Any]) -> None:
    validate_document(catalog, CATALOG_SCHEMA_RESOURCE)


def build_catalog(routes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Assemble the catalog payload written to catalog.json."""
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "OpenStreetMap via local extracts and Overpass API",
        "license": "ODbL",
        "routes": list(routes),
    }


def export_route_catalog(routes: Sequence[dict[str, Any]], output_path: str) -> None:
    """Write catalog.json containing the curated tracks."""
    catalog = build_catalog(routes)
    validate_catalog(catalog)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
