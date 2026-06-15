#!/usr/bin/env python3
"""Tests mockes du traitement par lots."""

import requests

import similar
from cache import SQLiteCache
from config import RESULT_SOURCE_KEY, SOURCE_API_LIVE


SAMPLE_PAYLOAD = {
    "SiteName": "example.com",
    "EstimatedMonthlyVisits": {"2026-04-01": 12345},
    "GlobalRank": {"Rank": 123},
}


class FakeRateController:
    def before_request(self):
        return 0

    def should_abort_batch(self):
        return False

    def on_success(self):
        pass

    def on_rate_limit(self, status_code):
        raise AssertionError(f"Rate limit inattendu dans ce test: {status_code}")


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = {}
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, endpoint, headers=None, timeout=None):
        self.calls.append({"endpoint": endpoint, "headers": headers or {}, "timeout": timeout})
        return next(self.responses)

    def close(self):
        pass


def test_batch_processing(monkeypatch, tmp_path):
    """Le batch traite les domaines un par un sans appel live reel."""
    cache = SQLiteCache(db_path=str(tmp_path / "cache.db"), duration_hours=24)
    session = FakeSession(
        [
            FakeResponse(200, SAMPLE_PAYLOAD),
            FakeResponse(200, SAMPLE_PAYLOAD),
            FakeResponse(200, SAMPLE_PAYLOAD),
        ]
    )
    progress_events = []

    monkeypatch.setattr(similar, "db_cache", cache)
    monkeypatch.setattr(similar, "CACHE_FILE", str(tmp_path / "legacy_cache.json"))
    monkeypatch.setattr(similar, "_get_session", lambda: (session, "UA-STABLE"))
    monkeypatch.setattr(similar, "_warm_up_session", lambda session, user_agent: None)
    monkeypatch.setattr(similar.time, "sleep", lambda seconds: None)

    results = similar.similarGetBatch(
        ["github.com", "stackoverflow.com", "google.com"],
        delay_between_requests=0.1,
        use_cache=True,
        progress_callback=lambda current, total, domain, result: progress_events.append((current, total, domain)),
        retry_count=1,
        rate_controller=FakeRateController(),
    )

    assert set(results) == {"github.com", "stackoverflow.com", "google.com"}
    assert all(payload[RESULT_SOURCE_KEY] == SOURCE_API_LIVE for payload in results.values())
    assert len(session.calls) == 3
    assert "domain=github.com" in session.calls[0]["endpoint"]
    assert progress_events[-1] == (3, 3, "google.com")
