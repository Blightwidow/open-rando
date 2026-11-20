"""How the walking-distance client reacts to what OSRM answers."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from open_rando.fetchers import routing
from open_rando.fetchers.routing import RoutingUnavailableError, fetch_pedestrian_distance_matrix

SOURCE = (48.5, 2.5)
DESTINATIONS = [(48.51, 2.51), (48.52, 2.52)]


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.payload = payload

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


@pytest.fixture(autouse=True)
def isolated_routing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routing, "OSRM_CACHE_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(routing, "RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(routing, "OSRM_COOLDOWN_SECONDS", 0)


def answer_with(monkeypatch: pytest.MonkeyPatch, response: FakeResponse) -> None:
    monkeypatch.setattr(routing.requests, "get", lambda *_args, **_kwargs: response)


def test_returns_one_distance_per_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    answer_with(monkeypatch, FakeResponse(200, {"code": "Ok", "distances": [[1200.0, None]]}))

    assert fetch_pedestrian_distance_matrix(SOURCE, DESTINATIONS) == [1200.0, None]


def test_off_network_source_yields_no_distances(monkeypatch: pytest.MonkeyPatch) -> None:
    answer_with(monkeypatch, FakeResponse(400, {"code": "NoSegment"}))

    assert fetch_pedestrian_distance_matrix(SOURCE, DESTINATIONS) == [None, None]


def test_raises_when_osrm_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise requests.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr(routing.requests, "get", refuse)

    with pytest.raises(RoutingUnavailableError, match="Makefile.osrm"):
        fetch_pedestrian_distance_matrix(SOURCE, DESTINATIONS)


def test_raises_when_osrm_stays_overloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    answer_with(monkeypatch, FakeResponse(429, {"code": "TooManyRequests"}))

    with pytest.raises(RoutingUnavailableError, match="HTTP 429"):
        fetch_pedestrian_distance_matrix(SOURCE, DESTINATIONS)


def test_raises_on_a_rejected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    answer_with(monkeypatch, FakeResponse(400, {"code": "TooBig"}))

    with pytest.raises(RoutingUnavailableError, match="code=TooBig"):
        fetch_pedestrian_distance_matrix(SOURCE, DESTINATIONS)


def test_raises_on_a_non_json_error_page(monkeypatch: pytest.MonkeyPatch) -> None:
    answer_with(monkeypatch, FakeResponse(502, ValueError("not json")))

    with pytest.raises(RoutingUnavailableError, match="without JSON"):
        fetch_pedestrian_distance_matrix(SOURCE, DESTINATIONS)


def test_serves_a_repeated_query_from_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    answer_with(monkeypatch, FakeResponse(200, {"code": "Ok", "distances": [[900.0, 1500.0]]}))
    fetch_pedestrian_distance_matrix(SOURCE, DESTINATIONS)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("OSRM called for a cached query")

    monkeypatch.setattr(routing.requests, "get", fail)

    assert fetch_pedestrian_distance_matrix(SOURCE, DESTINATIONS) == [900.0, 1500.0]
