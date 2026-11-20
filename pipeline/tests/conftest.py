from collections.abc import Iterator

import pytest

from open_rando.fetchers import osm_source


@pytest.fixture(autouse=True)
def fresh_osm_source() -> Iterator[None]:
    """`get_osm_source` is chosen once per run; each test is its own run."""
    osm_source.get_osm_source.cache_clear()
    yield
    osm_source.get_osm_source.cache_clear()
