from collections.abc import Iterator
from pathlib import Path

import pytest

from open_rando.exporters import run_inputs
from open_rando.fetchers import osm_source


@pytest.fixture(autouse=True)
def fresh_osm_source() -> Iterator[None]:
    """`get_osm_source` is chosen once per run; each test is its own run."""
    osm_source.get_osm_source.cache_clear()
    yield
    osm_source.get_osm_source.cache_clear()


@pytest.fixture(autouse=True)
def isolated_run_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep stage runs in tests from writing the real data directory."""
    path = tmp_path / "run-inputs.json"
    monkeypatch.setattr(run_inputs, "RUN_INPUTS_PATH", str(path))
    return path
