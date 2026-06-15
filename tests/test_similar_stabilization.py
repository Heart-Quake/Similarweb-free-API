import asyncio
import itertools
import json
import time
from pathlib import Path

import pytest
import requests

import similar
from core_async import AsyncSimilarClient
from cache import SQLiteCache
from config import (
    APP_VERSION,
    CACHE_STATUS_KEY,
    CACHE_STATUS_STALE,
    DEFAULT_RETRY_COUNT,
    ERROR_KIND_KEY,
    ERROR_KIND_PROVIDER_BLOCKED,
    FALLBACK_REASON_KEY,
    FALLBACK_REASON_PROVIDER_BLOCKED,
    MAX_CONSECUTIVE_RATE_LIMITS,
    NETWORK_PRESETS,
    RESULT_SOURCE_KEY,
    SOURCE_API_LIVE,
    SOURCE_CACHE_FRESH,
    SOURCE_CACHE_STALE,
    SOURCE_SIMILARWEB_BLOCKED,
)


SAMPLE_PAYLOAD = {
    "SiteName": "example.com",
    "EstimatedMonthlyVisits": {"2026-04-01": 12345},
    "GlobalRank": {"Rank": 123},
}


class FakeRateController:
    def __init__(self, cooldown_seconds=0):
        self.cooldown_seconds = cooldown_seconds
        self.successes = 0
        self.rate_limits = []

    def before_request(self):
        return self.cooldown_seconds

    def should_abort_batch(self):
        return len(self.rate_limits) >= 1 or self.cooldown_seconds > 0

    def on_success(self):
        self.successes += 1

    def on_rate_limit(self, status_code):
        self.rate_limits.append(status_code)


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

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
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        pass


class FakeAioResponse:
    def __init__(self, status, payload=None, headers=None, text=""):
        self.status = status
        self._payload = payload or {}
        self.headers = headers or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return self._text

    async def read(self):
        return b""

    def raise_for_status(self):
        raise RuntimeError(f"HTTP {self.status}")


class FakeAioSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, endpoint, headers=None, proxy=None):
        self.calls.append({"endpoint": endpoint, "headers": headers or {}, "proxy": proxy})
        return next(self.responses)


@pytest.fixture
def isolated_similar(monkeypatch, tmp_path):
    cache = SQLiteCache(db_path=str(tmp_path / "cache.db"), duration_hours=24)
    monkeypatch.setattr(similar, "db_cache", cache)
    monkeypatch.setattr(similar, "CACHE_FILE", str(tmp_path / "legacy_cache.json"))
    monkeypatch.setattr(similar, "HISTORY_FILE", str(tmp_path / "history.json"))
    monkeypatch.setattr(similar, "_warm_up_session", lambda session, user_agent: None)
    monkeypatch.setattr(similar.time, "sleep", lambda seconds: None)
    return cache


def install_fake_session(monkeypatch, responses):
    session = FakeSession(responses)
    monkeypatch.setattr(similar, "_get_session", lambda: (session, "UA-STABLE"))
    return session


def cloudfront_response():
    return FakeResponse(
        403,
        headers={"server": "CloudFront", "x-cache": "Error from cloudfront"},
        text="Request blocked. The request could not be satisfied.",
    )


def test_live_200_marks_api_live_and_uses_stable_user_agent(monkeypatch, isolated_similar):
    session = install_fake_session(monkeypatch, [FakeResponse(200, payload=SAMPLE_PAYLOAD)])
    controller = FakeRateController()

    result = similar.similarGet("https://www.example.com", use_cache=False, retry_count=1, rate_controller=controller)

    assert result[RESULT_SOURCE_KEY] == SOURCE_API_LIVE
    assert result["SiteName"] == "example.com"
    assert controller.successes == 1
    assert session.calls[0]["headers"]["User-Agent"] == "UA-STABLE"


def test_404_returns_domain_not_found(monkeypatch, isolated_similar):
    install_fake_session(monkeypatch, [FakeResponse(404)])

    result = similar.similarGet("missing.example", use_cache=False, retry_count=1, rate_controller=FakeRateController())

    assert result["error"] == "Domain not found"
    assert result["status_code"] == 404


def test_cloudfront_403_stops_without_retry(monkeypatch, isolated_similar):
    session = install_fake_session(monkeypatch, [cloudfront_response(), FakeResponse(200, payload=SAMPLE_PAYLOAD)])
    controller = FakeRateController()

    result = similar.similarGet("example.com", use_cache=False, retry_count=3, rate_controller=controller)

    assert result[RESULT_SOURCE_KEY] == SOURCE_SIMILARWEB_BLOCKED
    assert result[ERROR_KIND_KEY] == ERROR_KIND_PROVIDER_BLOCKED
    assert result["status_code"] == 403
    assert len(session.calls) == 1
    assert controller.rate_limits == [403]


def test_429_retries_with_same_user_agent(monkeypatch, isolated_similar):
    session = install_fake_session(monkeypatch, [FakeResponse(429), FakeResponse(200, payload=SAMPLE_PAYLOAD)])
    controller = FakeRateController()

    result = similar.similarGet("example.com", use_cache=False, retry_count=2, rate_controller=controller)

    assert result[RESULT_SOURCE_KEY] == SOURCE_API_LIVE
    assert len(session.calls) == 2
    assert {call["headers"]["User-Agent"] for call in session.calls} == {"UA-STABLE"}
    assert controller.rate_limits == [429]


def test_timeout_returns_error(monkeypatch, isolated_similar):
    install_fake_session(monkeypatch, [requests.Timeout("timed out")])

    result = similar.similarGet("example.com", use_cache=False, retry_count=1, rate_controller=FakeRateController())

    assert "timed out" in result["error"]
    assert result["domain"] == "example.com"


def test_fresh_cache_is_served_without_network(monkeypatch, isolated_similar):
    isolated_similar.set("example.com", SAMPLE_PAYLOAD)
    session = install_fake_session(monkeypatch, [FakeResponse(500)])

    result = similar.similarGet("example.com", use_cache=True, retry_count=1, rate_controller=FakeRateController())

    assert result[RESULT_SOURCE_KEY] == SOURCE_CACHE_FRESH
    assert result["SiteName"] == "example.com"
    assert session.calls == []


def test_stale_cache_is_explicit_fallback_on_cloudfront_block(monkeypatch, tmp_path):
    stale_cache = SQLiteCache(db_path=str(tmp_path / "stale.db"), duration_hours=0)
    stale_cache.set("example.com", SAMPLE_PAYLOAD)
    monkeypatch.setattr(similar, "db_cache", stale_cache)
    monkeypatch.setattr(similar, "CACHE_FILE", str(tmp_path / "legacy_cache.json"))
    monkeypatch.setattr(similar, "_warm_up_session", lambda session, user_agent: None)
    monkeypatch.setattr(similar.time, "sleep", lambda seconds: None)
    install_fake_session(monkeypatch, [cloudfront_response()])

    result = similar.similarGet("example.com", use_cache=True, retry_count=3, rate_controller=FakeRateController())

    assert result[RESULT_SOURCE_KEY] == SOURCE_CACHE_STALE
    assert result[CACHE_STATUS_KEY] == CACHE_STATUS_STALE
    assert result[FALLBACK_REASON_KEY] == FALLBACK_REASON_PROVIDER_BLOCKED
    assert result["status_code"] == 403


def test_batch_healthcheck_200_then_live_domain_allowed(monkeypatch, isolated_similar):
    session = install_fake_session(monkeypatch, [FakeResponse(200), FakeResponse(200, payload=SAMPLE_PAYLOAD)])
    controller = FakeRateController()

    results = similar.similarGetBatch(
        ["example.com"],
        delay_between_requests=0.1,
        use_cache=False,
        retry_count=1,
        rate_controller=controller,
        preflight_check=True,
    )

    assert results["example.com"][RESULT_SOURCE_KEY] == SOURCE_API_LIVE
    assert len(session.calls) == 2
    assert "domain=github.com" in session.calls[0]["endpoint"]
    assert "domain=example.com" in session.calls[1]["endpoint"]


def test_batch_healthcheck_cloudfront_blocks_before_live_domains(monkeypatch, isolated_similar):
    session = install_fake_session(monkeypatch, [cloudfront_response(), FakeResponse(200, payload=SAMPLE_PAYLOAD)])
    controller = FakeRateController()
    domains = [f"example-{index}.com" for index in range(10)]

    results = similar.similarGetBatch(
        domains,
        delay_between_requests=0.1,
        use_cache=False,
        retry_count=3,
        rate_controller=controller,
        preflight_check=True,
    )

    assert len(results) == 10
    assert len(session.calls) == 1
    assert all(payload["status_code"] == 403 for payload in results.values())
    assert all(payload[RESULT_SOURCE_KEY] == SOURCE_SIMILARWEB_BLOCKED for payload in results.values())


def test_batch_resume_skips_fresh_cache_and_keeps_uncached_blocked(monkeypatch, isolated_similar):
    isolated_similar.set("cached.com", SAMPLE_PAYLOAD)
    session = install_fake_session(monkeypatch, [cloudfront_response(), FakeResponse(200, payload=SAMPLE_PAYLOAD)])
    controller = FakeRateController()

    results = similar.similarGetBatch(
        ["cached.com", "uncached.com"],
        delay_between_requests=0.1,
        use_cache=True,
        retry_count=1,
        rate_controller=controller,
        preflight_check=True,
    )

    assert results["cached.com"][RESULT_SOURCE_KEY] == SOURCE_CACHE_FRESH
    assert results["uncached.com"][RESULT_SOURCE_KEY] == SOURCE_SIMILARWEB_BLOCKED
    assert len(session.calls) == 1


def test_batch_aborts_after_global_block_without_retrying_all_domains(monkeypatch, isolated_similar):
    session = install_fake_session(monkeypatch, itertools.repeat(cloudfront_response()))
    controller = FakeRateController()
    domains = [f"example-{index}.com" for index in range(10)]

    results = similar.similarGetBatch(
        domains,
        delay_between_requests=0.1,
        use_cache=False,
        retry_count=3,
        rate_controller=controller,
        preflight_check=True,
        abort_on_provider_block=True,
    )

    assert len(results) == 10
    assert len(session.calls) == 1
    assert all(payload["status_code"] == 403 for payload in results.values())


def test_patient_batch_skips_preflight_and_collects_domains(monkeypatch, isolated_similar):
    session = install_fake_session(monkeypatch, [FakeResponse(200, payload=SAMPLE_PAYLOAD), FakeResponse(200, payload=SAMPLE_PAYLOAD)])
    controller = FakeRateController()

    results = similar.similarGetBatch(
        ["example.com", "another-example.com"],
        delay_between_requests=0.1,
        use_cache=False,
        retry_count=1,
        rate_controller=controller,
    )

    assert results["example.com"][RESULT_SOURCE_KEY] == SOURCE_API_LIVE
    assert results["another-example.com"][RESULT_SOURCE_KEY] == SOURCE_API_LIVE
    assert len(session.calls) == 2
    assert "domain=github.com" not in session.calls[0]["endpoint"]
    assert "domain=example.com" in session.calls[0]["endpoint"]
    assert "domain=another-example.com" in session.calls[1]["endpoint"]


def test_patient_batch_retries_plain_403_without_aborting_next_domain(monkeypatch, isolated_similar):
    session = install_fake_session(
        monkeypatch,
        [FakeResponse(403), FakeResponse(200, payload=SAMPLE_PAYLOAD), FakeResponse(200, payload=SAMPLE_PAYLOAD)],
    )
    controller = FakeRateController()

    results = similar.similarGetBatch(
        ["example.com", "another-example.com"],
        delay_between_requests=0.1,
        use_cache=False,
        retry_count=2,
        rate_controller=controller,
    )

    assert results["example.com"][RESULT_SOURCE_KEY] == SOURCE_API_LIVE
    assert results["another-example.com"][RESULT_SOURCE_KEY] == SOURCE_API_LIVE
    assert len(session.calls) == 3
    assert "domain=github.com" not in session.calls[0]["endpoint"]


def test_stale_fallback_is_not_saved_to_history(monkeypatch, tmp_path):
    history_file = tmp_path / "history.json"
    monkeypatch.setattr(similar, "HISTORY_FILE", str(history_file))
    stale_payload = dict(SAMPLE_PAYLOAD)
    stale_payload[CACHE_STATUS_KEY] = CACHE_STATUS_STALE

    similar.save_many_to_history([("example.com", stale_payload, "2026-04")])

    if history_file.exists():
        assert json.loads(history_file.read_text(encoding="utf-8")) == {}


def test_long_secure_preset_is_default_and_single_attempt():
    default_name = next(iter(NETWORK_PRESETS))
    default_preset = NETWORK_PRESETS[default_name]

    assert default_name == "Collecte patiente fiable"
    assert default_preset["max_concurrency"] == 1
    assert default_preset["delay"] >= 60
    assert DEFAULT_RETRY_COUNT == 1
    assert MAX_CONSECUTIVE_RATE_LIMITS == 1


def test_runtime_version_marker_is_exposed_in_ui_source():
    source = (Path(__file__).resolve().parents[1] / "streamlit_app.py").read_text(encoding="utf-8")

    assert APP_VERSION
    assert "APP_VERSION" in source
    assert "Version chargee / demarrage serveur" in source


def test_rate_state_plain_403_does_not_open_persisted_cooldown(tmp_path):
    from rate_state import RateLimitController

    db_path = str(tmp_path / "rate.db")
    controller = RateLimitController(db_path=db_path)
    controller.on_rate_limit(403)

    snapshot = controller.get_snapshot()
    reloaded_snapshot = RateLimitController(db_path=db_path).get_snapshot()

    assert snapshot.state == "HALF_OPEN"
    assert snapshot.hard_cooldown_until == 0
    assert reloaded_snapshot.hard_cooldown_until == pytest.approx(snapshot.hard_cooldown_until)


def test_rate_state_provider_403_opens_persisted_cooldown(tmp_path):
    from rate_state import RateLimitController

    db_path = str(tmp_path / "rate.db")
    controller = RateLimitController(db_path=db_path)
    controller.on_rate_limit(403, provider_blocked=True)

    snapshot = controller.get_snapshot()
    reloaded_snapshot = RateLimitController(db_path=db_path).get_snapshot()

    assert snapshot.state == "OPEN"
    assert snapshot.hard_cooldown_until > time.time()
    assert reloaded_snapshot.hard_cooldown_until == pytest.approx(snapshot.hard_cooldown_until)


def test_plain_403_can_retry_without_opening_global_cooldown(monkeypatch, isolated_similar, tmp_path):
    from rate_state import RateLimitController

    controller = RateLimitController(db_path=str(tmp_path / "rate.db"))
    session = install_fake_session(monkeypatch, [FakeResponse(403), FakeResponse(200, payload=SAMPLE_PAYLOAD)])

    result = similar.similarGet("example.com", use_cache=False, retry_count=2, rate_controller=controller)

    assert result[RESULT_SOURCE_KEY] == SOURCE_API_LIVE
    assert len(session.calls) == 2
    assert controller.get_snapshot().state == "HALF_OPEN"
    assert controller.get_snapshot().hard_cooldown_until == 0


def test_async_plain_403_can_retry_without_opening_global_cooldown(tmp_path):
    from rate_state import RateLimitController

    controller = RateLimitController(db_path=str(tmp_path / "rate.db"))
    session = FakeAioSession([FakeAioResponse(403), FakeAioResponse(200, payload=SAMPLE_PAYLOAD)])
    client = AsyncSimilarClient(
        cache=None,
        max_concurrency=1,
        delay_range=(0, 0),
        rate_controller=controller,
    )
    client._warmed_sessions.add(id(session))

    result = asyncio.run(client.fetch("example.com", retry_count=2, session=session, use_cache=False))

    assert result[RESULT_SOURCE_KEY] == SOURCE_API_LIVE
    assert len(session.calls) == 2
    assert controller.get_snapshot().state == "HALF_OPEN"
    assert controller.get_snapshot().hard_cooldown_until == 0
