from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("open_rando")

# Keep the tail of the traceback: the frames closest to the error say which
# fetcher timed out, the outer frames are always the same pipeline loop.
TRACEBACK_MAX_LINES = 40


def build_failure_entry(
    route_ref: str,
    relation_ids: list[int],
    error: BaseException,
    previous_entry: dict[str, Any] | None = None,
    failed_at: str | None = None,
) -> dict[str, Any]:
    """Describe one route failure, carrying over the attempt history."""
    timestamp = failed_at or datetime.now(UTC).isoformat()
    traceback_lines = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    ).splitlines()
    return {
        "ref": route_ref,
        "relation_ids": relation_ids,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "traceback": "\n".join(traceback_lines[-TRACEBACK_MAX_LINES:]),
        "first_failed_at": (previous_entry or {}).get("first_failed_at", timestamp),
        "last_failed_at": timestamp,
        "attempts": int((previous_entry or {}).get("attempts", 0)) + 1,
    }


def load_failure_log(path: str) -> dict[str, dict[str, Any]]:
    """Read the failure log, keyed by route ref. Missing or corrupt file -> empty."""
    log_path = Path(path)
    if not log_path.exists():
        return {}
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Failure log %s is not valid JSON, starting fresh", path)
        return {}
    return {str(entry["ref"]): entry for entry in payload.get("failures", [])}


def export_failure_log(entries: dict[str, dict[str, Any]], path: str) -> None:
    """Write the failure log, sorted by ref so diffs stay readable."""
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"failures": [entries[route_ref] for route_ref in sorted(entries)]}
    log_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
