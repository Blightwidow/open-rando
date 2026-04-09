from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from open_rando.config import (
    SNCF_CACHE_DIRECTORY,
    SNCF_CACHE_TTL_SECONDS,
    SNCF_STATIONS_URL,
)

logger = logging.getLogger("open_rando")

CACHE_FILENAME = "gares-de-voyageurs.json"


def fetch_sncf_stations() -> list[dict[str, Any]]:
    """Download the official SNCF passenger station list, with disk caching.

    Returns the parsed JSON array of station records. On network error,
    falls back to stale cache if available, otherwise returns an empty list.
    """
    cache_path = _cache_path()

    cached = _read_cache(cache_path)
    if cached is not None:
        logger.info("Using cached SNCF station list (%d records)", len(cached))
        return cached

    try:
        response = requests.get(SNCF_STATIONS_URL, timeout=60)
        response.raise_for_status()
        records: list[dict[str, Any]] = response.json()
        _write_cache(cache_path, records)
        logger.info("Fetched %d SNCF stations from open data API", len(records))
        return records
    except (requests.RequestException, ValueError) as error:
        logger.warning("Failed to fetch SNCF stations: %s", error)
        stale = _read_cache(cache_path, ignore_ttl=True)
        if stale is not None:
            logger.warning("Using stale SNCF cache (%d records)", len(stale))
            return stale
        logger.warning("No SNCF cache available, station filtering will be skipped")
        return []


def build_sncf_code_set(records: list[dict[str, Any]]) -> set[str]:
    """Build a lookup set of SNCF station codes from the dataset.

    Includes both trigrammes (libellecourt, matching OSM ref:SNCF)
    and UIC codes (codes_uic, matching OSM uic_ref).
    """
    codes: set[str] = set()

    for record in records:
        trigramme = record.get("libellecourt")
        if trigramme:
            codes.add(str(trigramme).strip())

        uic_code = record.get("codes_uic")
        if uic_code:
            raw = str(uic_code).strip()
            codes.add(raw)
            # SNCF uses 8-digit UIC codes (UIC-7 + check digit),
            # while OSM uic_ref typically uses 7-digit UIC codes.
            # Store both the 8-digit and 7-digit (without check digit) variants.
            if len(raw) == 8:
                codes.add(raw[:7])  # UIC-7 (drop check digit)
            if raw.startswith("87") and len(raw) >= 4:
                codes.add(raw[2:])
            elif len(raw) <= 6:
                codes.add("87" + raw)

    return codes


def _cache_path() -> Path:
    directory = Path(SNCF_CACHE_DIRECTORY).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / CACHE_FILENAME


def _read_cache(
    path: Path,
    ignore_ttl: bool = False,
) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None

    if not ignore_ttl:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > SNCF_CACHE_TTL_SECONDS:
            logger.info("SNCF cache expired (%.0fs old)", age_seconds)
            return None

    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _write_cache(path: Path, data: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")
    logger.info("Cached SNCF station list to %s", path)
