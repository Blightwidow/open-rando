"""Record which input versions each stage read, so two runs can be compared.

Each stage writes its own entry into `run-inputs.json` (the last run of that
stage wins); the `catalog` stage copies the file into `run-report.json`. A
catalog diff can then be traced to its cause: a newer OSM extract, a changed
GTFS feed, a different OSRM graph, or a code change.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_rando.config import (
    OSM_EXTRACT_DIRECTORY,
    OSRM_GRAPH_DIRECTORY,
    OSRM_HOST,
    RUN_INPUTS_PATH,
    SNCF_CACHE_DIRECTORY,
    SRTM_BASE_URL,
)
from open_rando.fetchers.osm_extract import OsmExtractIndex
from open_rando.fetchers.osm_source import LocalExtractSource, OsmSource
from open_rando.json_types import JsonObject, load_json_object

logger = logging.getLogger("open_rando")

REPOSITORY_DIRECTORY = Path(__file__).resolve().parents[4]


def record_stage_inputs(
    stage: str,
    inputs: JsonObject,
    path: Path | None = None,
) -> None:
    """Store the inputs of one stage run, replacing that stage's previous entry."""
    inputs_path = path or Path(RUN_INPUTS_PATH).expanduser()
    recorded = load_run_inputs(inputs_path)
    recorded[stage] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "code_version": code_version(),
        **inputs,
    }
    inputs_path.parent.mkdir(parents=True, exist_ok=True)
    inputs_path.write_text(json.dumps(recorded, indent=2, sort_keys=True), encoding="utf-8")


def load_run_inputs(path: Path | None = None) -> JsonObject:
    inputs_path = path or Path(RUN_INPUTS_PATH).expanduser()
    if not inputs_path.exists():
        return {}
    try:
        return load_json_object(inputs_path.read_text(encoding="utf-8"))
    except ValueError:
        logger.warning("Unreadable %s, starting a new one", inputs_path)
        return {}


def code_version() -> JsonObject:
    """Git commit of the pipeline code, and whether tracked files were modified."""
    try:
        commit = _git("rev-parse", "HEAD")
        modified = bool(_git("status", "--porcelain", "--untracked-files=no"))
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "modified": None}
    return {"commit": commit, "modified": modified}


def osm_inputs(source: OsmSource) -> JsonObject:
    """Which OSM data the run read: source, extract file, index layers."""
    inputs: JsonObject = {"source": source.name}
    if not isinstance(source, LocalExtractSource):
        return inputs
    inputs["extract_files"] = [
        file_version(path)
        for path in sorted(Path(OSM_EXTRACT_DIRECTORY).expanduser().glob("*-latest.osm.pbf"))
    ]
    index = OsmExtractIndex.open_for_reading(source.index_path)
    if index is not None:
        try:
            inputs["index_layers"] = index.layer_summary()
        finally:
            index.close()
    inputs["border_fallback_relations"] = sorted(source.border_fallback_relations)
    return inputs


def elevation_inputs() -> JsonObject:
    return {"srtm_base_url": SRTM_BASE_URL}


def sncf_inputs() -> JsonObject:
    cache_files = sorted(Path(SNCF_CACHE_DIRECTORY).expanduser().glob("*.json"))
    return {"sncf_cache_files": [file_version(path) for path in cache_files]}


def routing_inputs(walking_refinement: bool) -> JsonObject:
    graph_files = sorted(Path(OSRM_GRAPH_DIRECTORY).expanduser().glob("*.osrm.mldgr"))
    return {
        "walking_refinement": walking_refinement,
        "osrm_url": OSRM_HOST,
        "osrm_graph_files": [file_version(path) for path in graph_files],
    }


def file_version(path: Path) -> JsonObject:
    """Name, size and modification time: enough to tell two downloads apart."""
    status = path.stat()
    return {
        "name": path.name,
        "size_bytes": status.st_size,
        "modified_at": datetime.fromtimestamp(status.st_mtime, UTC).isoformat(),
    }


def summarize_inputs_for_log(inputs: JsonObject) -> list[str]:
    """One line per stage, for the end-of-run log."""
    lines: list[str] = []
    for stage, stage_inputs in sorted(inputs.items()):
        version: dict[str, Any] = stage_inputs.get("code_version") or {}
        commit = (version.get("commit") or "unknown")[:8]
        modified = " (modified)" if version.get("modified") else ""
        lines.append(f"{stage}: {stage_inputs.get('recorded_at', '?')} at {commit}{modified}")
    return lines


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPOSITORY_DIRECTORY), *arguments],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return completed.stdout.strip()
