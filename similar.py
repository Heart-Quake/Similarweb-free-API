from __future__ import annotations

import json
import os
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

import requests

from cache import SQLiteCache
from config import (
    API_ENDPOINT_TEMPLATE,
    CACHE_DURATION_HOURS,
    CACHE_STATUS_FRESH,
    CACHE_STATUS_STALE,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TIMEOUT_SECONDS,
    ERROR_KIND_KEY,
    ERROR_KIND_RATE_LIMITED,
    FALLBACK_REASON_PROVIDER_BLOCKED,
    HEALTHCHECK_DOMAIN,
    HISTORY_LIMIT_PER_DOMAIN,
    MAX_CONSECUTIVE_RATE_LIMITS,
    SOURCE_API_LIVE,
    SOURCE_CACHE_FRESH,
    SOURCE_CACHE_STALE,
    build_provider_blocked_result,
    WARMUP_URL,
    build_request_headers,
    build_warmup_headers,
    get_logger,
    get_random_user_agent,
    is_cloudfront_block,
    is_provider_blocked_payload,
    is_stale_fallback_payload,
    mark_payload_source,
    strip_internal_metadata,
)
from rate_state import get_controller

logger = get_logger("sync")

CACHE_FILE = 'similarweb_cache.json'
HISTORY_FILE = 'similarweb_history.json'


db_cache = SQLiteCache(duration_hours=CACHE_DURATION_HOURS)

_session_lock = threading.Lock()
_session: Optional[requests.Session] = None
_session_warmed: bool = False
_session_user_agent: Optional[str] = None


def _reset_session_locked() -> None:
    """Recree une identite HTTP complete: session, cookies et User-Agent."""
    global _session, _session_warmed, _session_user_agent
    if _session is not None:
        try:
            _session.close()
        except requests.RequestException:
            pass
    _session = requests.Session()
    _session_user_agent = get_random_user_agent()
    _session_warmed = False


def reset_session() -> None:
    with _session_lock:
        _reset_session_locked()


def _get_session() -> tuple[requests.Session, str]:
    """Retourne une Session reutilisable et son User-Agent stable.

    Conserver la meme session permet de garder les cookies poses par le CDN
    Similarweb. Le User-Agent reste stable pour eviter un fingerprint incoherent.
    """
    global _session, _session_user_agent
    with _session_lock:
        if _session is None or _session_user_agent is None:
            _reset_session_locked()
        return _session, _session_user_agent


def _warm_up_session(session: requests.Session, user_agent: str) -> None:
    """Visite la home similarweb.com une fois pour recuperer les cookies CDN."""
    global _session_warmed
    if _session_warmed:
        return
    try:
        session.get(WARMUP_URL, headers=build_warmup_headers(user_agent), timeout=10)
    except requests.RequestException as error:
        logger.debug("Session warm-up failed (non-fatal): %s", error)
    finally:
        _session_warmed = True


def load_json_cache():
    # Conserve la compatibilite avec l'ancien cache JSON.
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as file_handle:
                return json.load(file_handle)
        except (OSError, ValueError, json.JSONDecodeError):
            logger.warning("Legacy JSON cache unreadable, ignoring")
            return {}
    return {}


def save_json_cache(cache):
    temp_path = CACHE_FILE + '.tmp'
    try:
        with open(temp_path, 'w', encoding='utf-8') as file_handle:
            json.dump(cache, file_handle, indent=2, ensure_ascii=False)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temp_path, CACHE_FILE)
    except (OSError, ValueError, json.JSONDecodeError):
        logger.exception("Unable to persist JSON cache")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def is_cache_valid(timestamp, duration_hours=CACHE_DURATION_HOURS):
    try:
        cache_time = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return False
    return datetime.now() - cache_time < timedelta(hours=duration_hours)


def extract_domain(website):
    parsed = urlparse(website)
    domain = parsed.netloc if parsed.netloc else parsed.path.split('/')[0]
    domain = domain.replace('www.', '')
    domain = domain.split('/')[0].split('?')[0].lower().strip()
    return domain


def _get_json_cache_entry(domain, cache_dict=None):
    source_cache = cache_dict if cache_dict is not None else load_json_cache()
    entry = source_cache.get(domain)
    if isinstance(entry, dict) and 'data' in entry and 'timestamp' in entry:
        return entry
    return None


def _get_cached_payload(domain, cache_dict=None, allow_stale=False):
    sqlite_payload = db_cache.get(domain, allow_stale=allow_stale)
    if sqlite_payload is not None:
        return sqlite_payload

    json_entry = _get_json_cache_entry(domain, cache_dict=cache_dict)
    if not json_entry:
        return None
    if allow_stale or is_cache_valid(json_entry.get('timestamp', '')):
        return json_entry.get('data')
    return None


def _save_cached_payload(domain, data, cache_dict=None):
    clean_data = strip_internal_metadata(data)
    db_cache.set(domain, clean_data)
    if cache_dict is not None:
        cache_dict[domain] = {
            'data': clean_data,
            'timestamp': datetime.now().isoformat(),
        }


def _build_fresh_cache_payload(payload):
    return mark_payload_source(payload, SOURCE_CACHE_FRESH, cache_status=CACHE_STATUS_FRESH)


def _build_live_payload(payload):
    return mark_payload_source(payload, SOURCE_API_LIVE)


def _build_stale_fallback(payload, fallback_reason=None, status_code=None):
    if not isinstance(payload, dict):
        return payload
    fallback = mark_payload_source(
        payload,
        SOURCE_CACHE_STALE,
        cache_status=CACHE_STATUS_STALE,
        fallback_reason=fallback_reason,
        status_code=status_code,
    )
    fallback['_fetched_at'] = datetime.now().isoformat()
    return fallback


def _read_response_preview(response: requests.Response, max_chars: int = 1200) -> str:
    try:
        return response.text[:max_chars]
    except (ValueError, requests.RequestException):
        return ""


def _handle_blocked_response(domain, stale_payload=None, status_code=403):
    reset_session()
    if stale_payload is not None:
        return _build_stale_fallback(
            stale_payload,
            fallback_reason=FALLBACK_REASON_PROVIDER_BLOCKED,
            status_code=status_code,
        )
    return build_provider_blocked_result(domain)


def _notify_rate_limit(controller, status_code: int, provider_blocked: bool = False) -> None:
    try:
        controller.on_rate_limit(status_code, provider_blocked=provider_blocked)
    except TypeError:
        controller.on_rate_limit(status_code)


def similarHealthCheck(domain=HEALTHCHECK_DOMAIN, rate_controller=None):
    """Sonde live minimale avant batch pour eviter de lancer un lot sur IP bloquee."""
    controller = rate_controller or get_controller()
    clean_domain = extract_domain(domain)

    cooldown_seconds = controller.before_request()
    if cooldown_seconds > 0:
        reset_session()
        return {
            "ok": False,
            "blocked": True,
            "domain": clean_domain,
            "status_code": 403,
            "error": "Circuit breaker cooldown active.",
            "cooldown_seconds": cooldown_seconds,
        }

    session, user_agent = _get_session()
    _warm_up_session(session, user_agent)
    endpoint = API_ENDPOINT_TEMPLATE.format(domain=clean_domain)

    try:
        response = session.get(
            endpoint,
            headers=build_request_headers(user_agent=user_agent),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        logger.warning("Health check failed for %s: %s", clean_domain, error)
        return {
            "ok": False,
            "blocked": False,
            "domain": clean_domain,
            "error": str(error),
        }

    if response.status_code == 200:
        controller.on_success()
        return {"ok": True, "blocked": False, "domain": clean_domain, "status_code": 200}

    if response.status_code in {403, 429}:
        response_preview = _read_response_preview(response) if response.status_code == 403 else ""
        blocked = response.status_code == 429 or is_cloudfront_block(response.status_code, response.headers, response_preview)
        _notify_rate_limit(controller, response.status_code, provider_blocked=blocked)
        if blocked:
            reset_session()
        return {
            "ok": False,
            "blocked": blocked,
            "domain": clean_domain,
            "status_code": response.status_code,
            "error": f"Health check HTTP {response.status_code}",
        }

    return {
        "ok": False,
        "blocked": False,
        "domain": clean_domain,
        "status_code": response.status_code,
        "error": f"Health check HTTP {response.status_code}",
    }


def similarGet(
    website,
    use_cache=True,
    retry_count=DEFAULT_RETRY_COUNT,
    delay_between_retries=2,
    cache_dict=None,
    rate_controller=None,
):
    domain = extract_domain(website)
    controller = rate_controller or get_controller()

    if use_cache:
        cached_payload = _get_cached_payload(domain, cache_dict=cache_dict, allow_stale=False)
        if cached_payload is not None:
            return _build_fresh_cache_payload(cached_payload)

    stale_payload = _get_cached_payload(domain, cache_dict=cache_dict, allow_stale=True) if use_cache else None
    cooldown_seconds = controller.before_request()
    if cooldown_seconds > 0:
        logger.warning("Circuit breaker active for %.1fs before %s", cooldown_seconds, domain)
        reset_session()
        if stale_payload is not None:
            return _build_stale_fallback(
                stale_payload,
                fallback_reason=FALLBACK_REASON_PROVIDER_BLOCKED,
                status_code=403,
            )
        return build_provider_blocked_result(
            domain,
            "Global rate limit detected. Circuit breaker cooldown active.",
        )

    endpoint = API_ENDPOINT_TEMPLATE.format(domain=domain)
    session, user_agent = _get_session()

    _warm_up_session(session, user_agent)

    # Jitter avant la requete pour lisser les pointes.
    time.sleep(random.uniform(0.5, 1.5))

    for attempt in range(retry_count):
        try:
            headers = build_request_headers(user_agent=user_agent)
            response = session.get(endpoint, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)

            if response.status_code == 200:
                data = response.json()
                if use_cache:
                    _save_cached_payload(domain, data, cache_dict=cache_dict)
                controller.on_success()
                return _build_live_payload(data)

            if response.status_code == 404:
                return {'error': 'Domain not found', 'domain': domain, 'status_code': 404}

            if response.status_code in {403, 429}:
                response_preview = _read_response_preview(response) if response.status_code == 403 else ""
                provider_blocked = is_cloudfront_block(response.status_code, response.headers, response_preview)
                _notify_rate_limit(controller, response.status_code, provider_blocked=provider_blocked)
                logger.warning(
                    "Rate limited (%s) on %s attempt=%d/%d",
                    response.status_code, domain, attempt + 1, retry_count,
                )
                if provider_blocked:
                    logger.warning("CloudFront provider block detected on %s", domain)
                    return _handle_blocked_response(domain, stale_payload, status_code=response.status_code)

                if attempt < retry_count - 1:
                    retry_base = 8 if response.status_code == 403 else 15
                    wait_time = delay_between_retries * (2 ** attempt) + random.uniform(retry_base, retry_base + 20)
                    time.sleep(wait_time)
                    continue
                if stale_payload is not None:
                    logger.info("Serving stale cache for %s after repeated %s", domain, response.status_code)
                    return _build_stale_fallback(stale_payload, status_code=response.status_code)
                return {
                    'error': f'HTTP {response.status_code} after retries',
                    'domain': domain,
                    'status_code': response.status_code,
                    ERROR_KIND_KEY: ERROR_KIND_RATE_LIMITED,
                }

            response.raise_for_status()
        except (requests.RequestException, ValueError) as error:
            logger.debug("Request error for %s attempt=%d: %s", domain, attempt + 1, error)
            if attempt < retry_count - 1:
                wait_time = delay_between_retries * (2 ** attempt)
                time.sleep(wait_time)
                continue
            if stale_payload is not None:
                return _build_stale_fallback(stale_payload)
            return {'error': str(error), 'domain': domain}

    if stale_payload is not None:
        return _build_stale_fallback(stale_payload)
    return {'error': 'Max retries exceeded', 'domain': domain}


def similarGetBatch(
    domains,
    delay_between_requests=2.0,
    use_cache=True,
    progress_callback=None,
    chunk_size=100,
    retry_count=DEFAULT_RETRY_COUNT,
    rate_controller=None,
):
    results = {}
    total = len(domains)
    cache_dict = load_json_cache() if use_cache else None
    consecutive_rate_limits = 0
    controller = rate_controller or get_controller()
    normalized_domains = []
    requires_live = False

    for domain in domains:
        domain_clean = extract_domain(domain)
        cached_payload = _get_cached_payload(domain_clean, cache_dict=cache_dict, allow_stale=False) if use_cache else None
        if cached_payload is None:
            requires_live = True
        normalized_domains.append((domain, domain_clean, cached_payload))

    health_result = {"ok": True}
    if requires_live:
        health_result = similarHealthCheck(rate_controller=controller)

    if requires_live and not health_result.get("ok"):
        blocked_message = (
            "IP/session bloquee par Similarweb. Aucun domaine live n'a ete lance."
            if health_result.get("blocked")
            else "Sonde Similarweb indisponible. Le lot live est suspendu par prudence."
        )
        for current_index, (_, domain_clean, cached_payload) in enumerate(normalized_domains, 1):
            if cached_payload is not None:
                result = _build_fresh_cache_payload(cached_payload)
            else:
                stale_payload = _get_cached_payload(domain_clean, cache_dict=cache_dict, allow_stale=True) if use_cache else None
                result = (
                    _build_stale_fallback(
                        stale_payload,
                        fallback_reason=FALLBACK_REASON_PROVIDER_BLOCKED,
                        status_code=403,
                    )
                    if stale_payload is not None
                    else build_provider_blocked_result(domain_clean, blocked_message)
                )
            results[domain_clean] = result
            if progress_callback:
                progress_callback(current_index, total, domain_clean, result)
        if use_cache and cache_dict is not None:
            save_json_cache(cache_dict)
        return results

    ordered_domains = [raw_domain for raw_domain, _, _ in normalized_domains]
    for chunk_start in range(0, total, chunk_size):
        chunk_end = min(chunk_start + chunk_size, total)
        chunk_domains = ordered_domains[chunk_start:chunk_end]

        for index, domain in enumerate(chunk_domains, 1):
            domain_clean = extract_domain(domain)
            current_index = chunk_start + index

            cached_payload = _get_cached_payload(domain_clean, cache_dict=cache_dict, allow_stale=False) if use_cache else None
            was_cached = cached_payload is not None
            if was_cached:
                result = _build_fresh_cache_payload(cached_payload)
            else:
                if controller.should_abort_batch():
                    stale_payload = _get_cached_payload(domain_clean, cache_dict=cache_dict, allow_stale=True) if use_cache else None
                    result = (
                        _build_stale_fallback(
                            stale_payload,
                            fallback_reason=FALLBACK_REASON_PROVIDER_BLOCKED,
                            status_code=403,
                        )
                        if stale_payload is not None
                        else build_provider_blocked_result(domain_clean)
                    )
                else:
                    result = similarGet(
                        domain,
                        use_cache=use_cache,
                        retry_count=retry_count,
                        delay_between_retries=max(2.0, float(delay_between_requests or 2.0)),
                        cache_dict=cache_dict,
                        rate_controller=controller,
                    )

            results[domain_clean] = result
            if progress_callback:
                progress_callback(current_index, total, domain_clean, result)

            is_rate_limited = isinstance(result, dict) and (
                result.get('status_code') in {403, 429}
                or str(result.get('error', '')).startswith('HTTP 403')
                or str(result.get('error', '')).startswith('HTTP 429')
                or is_provider_blocked_payload(result)
            )
            if is_rate_limited:
                consecutive_rate_limits += 1
            else:
                consecutive_rate_limits = 0

            if consecutive_rate_limits >= MAX_CONSECUTIVE_RATE_LIMITS:
                for remaining_domain in chunk_domains[index:]:
                    remaining_clean = extract_domain(remaining_domain)
                    stale_payload = _get_cached_payload(remaining_clean, cache_dict=cache_dict, allow_stale=True) if use_cache else None
                    results[remaining_clean] = (
                        _build_stale_fallback(
                            stale_payload,
                            fallback_reason=FALLBACK_REASON_PROVIDER_BLOCKED,
                            status_code=403,
                        )
                        if stale_payload is not None
                        else build_provider_blocked_result(
                            remaining_clean,
                            "Global rate limit detected. Batch aborted to avoid wasting time.",
                        )
                    )
                    if progress_callback:
                        progress_callback(len(results), total, remaining_clean, results[remaining_clean])
                if use_cache and cache_dict is not None:
                    save_json_cache(cache_dict)
                return results

            if current_index < total and not was_cached:
                delay = max(0.15, float(delay_between_requests or 2.0) + random.uniform(-0.5, 0.5))
                time.sleep(delay)

        if use_cache and cache_dict is not None:
            save_json_cache(cache_dict)

        if chunk_end < total:
            time.sleep(max(0.15, float(delay_between_requests or 2.0) * 2))

    if use_cache and cache_dict is not None:
        save_json_cache(cache_dict)

    return results


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as file_handle:
                return json.load(file_handle)
        except (OSError, ValueError, json.JSONDecodeError):
            logger.warning("History file unreadable, starting fresh")
            return {}
    return {}


def save_history(history):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as file_handle:
            json.dump(history, file_handle, indent=2, ensure_ascii=False)
    except (OSError, ValueError, json.JSONDecodeError):
        logger.exception("Unable to persist history")


def save_to_history(domain, data, period_label=None):
    save_many_to_history([(domain, data, period_label)])


def save_many_to_history(entries):
    valid_entries = [
        (domain, strip_internal_metadata(data), period_label)
        for domain, data, period_label in entries
        if (
            data
            and not isinstance(data, bool)
            and isinstance(data, dict)
            and 'error' not in data
            and not is_stale_fallback_payload(data)
        )
    ]
    if not valid_entries:
        return

    history = load_history()
    timestamp = datetime.now().isoformat()
    date_label = datetime.now().strftime('%Y-%m-%d')
    default_period = datetime.now().strftime('%Y-%m')

    for domain, data, period_label in valid_entries:
        domain_clean = extract_domain(domain)
        if domain_clean not in history:
            history[domain_clean] = []

        history_entry = {
            'timestamp': timestamp,
            'date': date_label,
            'period': period_label or default_period,
            'data': data,
        }

        history[domain_clean].append(history_entry)
        history[domain_clean] = history[domain_clean][-HISTORY_LIMIT_PER_DOMAIN:]

    save_history(history)


def get_history_for_domain(domain, start_date=None, end_date=None, period=None):
    history = load_history()
    domain_clean = extract_domain(domain)

    if domain_clean not in history:
        return []

    entries = history[domain_clean]

    if period:
        entries = [entry for entry in entries if entry.get('period') == period]

    if start_date or end_date:
        filtered = []
        for entry in entries:
            entry_date = datetime.fromisoformat(entry['timestamp'])
            if start_date:
                start_value = datetime.fromisoformat(start_date) if isinstance(start_date, str) else start_date
                if entry_date < start_value:
                    continue
            if end_date:
                end_value = datetime.fromisoformat(end_date) if isinstance(end_date, str) else end_date
                if entry_date > end_value:
                    continue
            filtered.append(entry)
        entries = filtered

    entries.sort(key=lambda item: item['timestamp'])
    return entries


def get_all_domains_in_history():
    history = load_history()
    return list(history.keys())


def compare_periods(domain, period1, period2):
    history1 = get_history_for_domain(domain, period=period1)
    history2 = get_history_for_domain(domain, period=period2)

    if not history1 or not history2:
        return None

    data1 = history1[-1]['data']
    data2 = history2[-1]['data']

    comparison = {
        'domain': domain,
        'period1': period1,
        'period2': period2,
        'data1': data1,
        'data2': data2,
        'changes': {},
    }

    if 'EstimatedMonthlyVisits' in data1 and 'EstimatedMonthlyVisits' in data2:
        visits1 = data1['EstimatedMonthlyVisits']
        visits2 = data2['EstimatedMonthlyVisits']

        if isinstance(visits1, dict) and isinstance(visits2, dict) and visits1 and visits2:
            latest1 = list(visits1.values())[-1]
            latest2 = list(visits2.values())[-1]
            if latest1 > 0:
                change_pct = ((latest2 - latest1) / latest1) * 100
                comparison['changes']['visits'] = {
                    'period1': latest1,
                    'period2': latest2,
                    'change': latest2 - latest1,
                    'change_percent': change_pct,
                }

    if 'GlobalRank' in data1 and 'GlobalRank' in data2:
        rank1 = data1['GlobalRank'].get('Rank', 0) if isinstance(data1['GlobalRank'], dict) else data1['GlobalRank']
        rank2 = data2['GlobalRank'].get('Rank', 0) if isinstance(data2['GlobalRank'], dict) else data2['GlobalRank']
        if rank1 and rank2:
            comparison['changes']['rank'] = {
                'period1': rank1,
                'period2': rank2,
                'change': rank2 - rank1,
            }

    return comparison
