"""Configuration partagee entre le client sync (similar.py) et async (core_async.py)."""
from __future__ import annotations

import logging
import os
import random

CACHE_DURATION_HOURS = 24
HISTORY_LIMIT_PER_DOMAIN = 1000
APP_VERSION = "2026-06-15-patient-sequential-batch-v2"
HEALTHCHECK_DOMAIN = "github.com"
MAX_CONSECUTIVE_RATE_LIMITS = 1
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RETRY_COUNT = 1
DEFAULT_LONG_COOLDOWN_SECONDS = 3600

NETWORK_PRESETS = {
    "Collecte patiente fiable": {
        "delay": 60.0,
        "max_concurrency": 1,
        "description": "Mode par defaut: un domaine a la fois, sans sonde bloquante, avec reprise par cache.",
    },
    "Collecte longue sécurisée": {
        "delay": 45.0,
        "max_concurrency": 1,
        "description": "Mode sequentiel prudent pour les lots moyens quand Similarweb repond deja correctement.",
    },
    "Rapide prudent": {
        "delay": 6.0,
        "max_concurrency": 2,
        "description": "Reserve aux petits lots quand la sonde Similarweb repond deja correctement.",
    },
    "Très prudent": {
        "delay": 90.0,
        "max_concurrency": 1,
        "description": "Cadence longue pour relancer une collecte apres une periode de blocage.",
    },
    "Test court rapide": {
        "delay": 2.0,
        "max_concurrency": 1,
        "description": "Verification courte sur quelques domaines, avec coupure immediate au blocage.",
    },
    "Personnalise": {
        "delay": None,
        "max_concurrency": None,
        "description": "Vous pilotez manuellement le delai. La collecte reste sequentielle.",
    },
}

API_ENDPOINT_TEMPLATE = "https://data.similarweb.com/api/v1/data?domain={domain}"
WARMUP_URL = "https://www.similarweb.com/"

RESULT_SOURCE_KEY = "_collection_source"
CACHE_STATUS_KEY = "_cache_status"
FETCHED_AT_KEY = "_fetched_at"
FALLBACK_REASON_KEY = "_fallback_reason"
ERROR_KIND_KEY = "_error_kind"

SOURCE_API_LIVE = "API live"
SOURCE_CACHE_FRESH = "Cache frais"
SOURCE_CACHE_STALE = "Cache expiré"
SOURCE_SIMILARWEB_BLOCKED = "Bloqué Similarweb"

CACHE_STATUS_FRESH = "fresh_cache"
CACHE_STATUS_STALE = "stale_fallback"

FALLBACK_REASON_PROVIDER_BLOCKED = "provider_blocked"
ERROR_KIND_PROVIDER_BLOCKED = "provider_blocked"
ERROR_KIND_RATE_LIMITED = "rate_limited"

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
)


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def build_request_headers(user_agent: str | None = None) -> dict[str, str]:
    """Entetes utilisees pour l'appel API Similarweb.

    `Accept-Encoding` volontairement limite a gzip/deflate: `requests` ne decode pas
    brotli sans dependance supplementaire, ce qui faisait echouer le JSON parsing sur
    certaines reponses CDN.
    """
    return {
        "User-Agent": user_agent or get_random_user_agent(),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.similarweb.com/",
        "Origin": "https://www.similarweb.com",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }


def build_warmup_headers(user_agent: str) -> dict[str, str]:
    """Entetes de warm-up alignes avec l'identite HTTP de la session."""
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }


def mark_payload_source(
    payload,
    source: str,
    cache_status: str | None = None,
    fallback_reason: str | None = None,
    status_code: int | None = None,
):
    """Ajoute les metadonnees d'origine sans muter le payload brut."""
    if not isinstance(payload, dict):
        return payload
    marked = dict(payload)
    marked[RESULT_SOURCE_KEY] = source
    if cache_status:
        marked[CACHE_STATUS_KEY] = cache_status
    if fallback_reason:
        marked[FALLBACK_REASON_KEY] = fallback_reason
    if status_code is not None and "status_code" not in marked:
        marked["status_code"] = status_code
    return marked


def strip_internal_metadata(payload):
    """Retire les metadonnees UI avant stockage historique/cache durable."""
    if not isinstance(payload, dict):
        return payload
    cleaned = dict(payload)
    for key in (RESULT_SOURCE_KEY, CACHE_STATUS_KEY, FETCHED_AT_KEY, FALLBACK_REASON_KEY, ERROR_KIND_KEY):
        cleaned.pop(key, None)
    return cleaned


def is_stale_fallback_payload(payload) -> bool:
    return isinstance(payload, dict) and payload.get(CACHE_STATUS_KEY) == CACHE_STATUS_STALE


def is_provider_blocked_payload(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    return (
        payload.get(ERROR_KIND_KEY) == ERROR_KIND_PROVIDER_BLOCKED
        or payload.get(FALLBACK_REASON_KEY) == FALLBACK_REASON_PROVIDER_BLOCKED
        or str(payload.get("error", "")).startswith("Global rate limit detected")
    )


def is_cloudfront_block(status_code: int, headers, body_text: str = "") -> bool:
    """Detecte le blocage global CloudFront renvoye par Similarweb."""
    if status_code != 403:
        return False
    header_blob = " ".join(
        str(headers.get(name, ""))
        for name in ("server", "via", "x-cache", "x-amz-cf-id", "x-amz-cf-pop")
        if hasattr(headers, "get")
    ).lower()
    body_lower = (body_text or "").lower()
    return (
        "cloudfront" in header_blob
        or "request blocked" in body_lower
        or "the request could not be satisfied" in body_lower
    )


def build_provider_blocked_result(domain: str, message: str | None = None) -> dict[str, object]:
    return {
        "error": message or "Global rate limit detected. Similarweb blocked this session.",
        "domain": domain,
        "status_code": 403,
        RESULT_SOURCE_KEY: SOURCE_SIMILARWEB_BLOCKED,
        ERROR_KIND_KEY: ERROR_KIND_PROVIDER_BLOCKED,
    }


_LOGGING_CONFIGURED = False


def configure_logging() -> logging.Logger:
    """Initialise le logger de l'app une fois par processus."""
    global _LOGGING_CONFIGURED
    logger = logging.getLogger("similarweb")
    if _LOGGING_CONFIGURED:
        return logger

    level_name = os.environ.get("SIMILARWEB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    _LOGGING_CONFIGURED = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    configure_logging()
    if name:
        return logging.getLogger(f"similarweb.{name}")
    return logging.getLogger("similarweb")
