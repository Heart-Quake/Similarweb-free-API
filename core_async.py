"""Client asynchrone pour l'API non-officielle Similarweb."""
from __future__ import annotations

import asyncio
import random
from datetime import datetime
from urllib.parse import urlparse

import aiohttp

from config import (
    API_ENDPOINT_TEMPLATE,
    CACHE_STATUS_FRESH,
    CACHE_STATUS_STALE,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TIMEOUT_SECONDS,
    ERROR_KIND_KEY,
    ERROR_KIND_RATE_LIMITED,
    FALLBACK_REASON_KEY,
    FALLBACK_REASON_PROVIDER_BLOCKED,
    HEALTHCHECK_DOMAIN,
    MAX_CONSECUTIVE_RATE_LIMITS,
    SOURCE_API_LIVE,
    SOURCE_CACHE_FRESH,
    SOURCE_CACHE_STALE,
    WARMUP_URL,
    build_provider_blocked_result,
    build_request_headers,
    build_warmup_headers,
    get_logger,
    get_random_user_agent,
    is_cloudfront_block,
    is_provider_blocked_payload,
    mark_payload_source,
    strip_internal_metadata,
)
from rate_state import get_controller

logger = get_logger("async")


class AsyncSimilarClient:
    """Pipeline asynchrone avec concurrence bornee, pacing et warm-up de session.

    Le warm-up cote async vise le meme objectif que cote sync: obtenir les cookies
    poses par le CDN Similarweb pour eviter les 403 sur IPs partagees.
    """

    def __init__(
        self,
        cache=None,
        proxy_list=None,
        max_concurrency=5,
        delay_range=(0.5, 1.5),
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        max_consecutive_rate_limits=MAX_CONSECUTIVE_RATE_LIMITS,
        rate_controller=None,
    ):
        self.cache = cache
        self.proxy_list = proxy_list or []
        self.max_concurrency = max(1, int(max_concurrency))
        self.delay_range = delay_range
        self.timeout_seconds = timeout_seconds
        self.max_consecutive_rate_limits = max(1, int(max_consecutive_rate_limits))
        self.rate_controller = rate_controller or get_controller()
        self.session_user_agent = get_random_user_agent()
        self._request_pace_lock = None
        self._request_pace_loop = None
        self._next_request_at = 0.0
        self._warmed_sessions: set[int] = set()

    def _get_random_proxy(self):
        return random.choice(self.proxy_list) if self.proxy_list else None

    def _build_stale_fallback(self, payload):
        if not isinstance(payload, dict):
            return payload
        fallback = mark_payload_source(payload, SOURCE_CACHE_STALE, cache_status=CACHE_STATUS_STALE)
        fallback["_fetched_at"] = datetime.now().isoformat()
        return fallback

    def _build_provider_stale_fallback(self, payload, status_code=403):
        fallback = self._build_stale_fallback(payload)
        if isinstance(fallback, dict):
            fallback["status_code"] = status_code
            fallback[FALLBACK_REASON_KEY] = FALLBACK_REASON_PROVIDER_BLOCKED
        return fallback

    def _build_fresh_cache_payload(self, payload):
        return mark_payload_source(payload, SOURCE_CACHE_FRESH, cache_status=CACHE_STATUS_FRESH)

    def _build_live_payload(self, payload):
        return mark_payload_source(payload, SOURCE_API_LIVE)

    def _reset_identity(self):
        self.session_user_agent = get_random_user_agent()
        self._warmed_sessions.clear()

    def _is_rate_limited(self, payload):
        if not isinstance(payload, dict):
            return False
        status_code = payload.get("status_code")
        error_text = str(payload.get("error", ""))
        return (
            status_code in {403, 429}
            or error_text.startswith("HTTP 403")
            or error_text.startswith("HTTP 429")
            or is_provider_blocked_payload(payload)
        )

    def _extract_domain(self, website):
        parsed = urlparse(website)
        domain = parsed.netloc if parsed.netloc else parsed.path.split("/")[0]
        domain = domain.replace("www.", "")
        domain = domain.split("/")[0].split("?")[0].lower().strip()
        return domain

    async def _wait_for_request_slot(self):
        loop = asyncio.get_running_loop()
        if self._request_pace_lock is None or self._request_pace_loop is not loop:
            self._request_pace_lock = asyncio.Lock()
            self._request_pace_loop = loop

        async with self._request_pace_lock:
            now = loop.time()
            if self._next_request_at > now:
                await asyncio.sleep(self._next_request_at - now)
            self._next_request_at = loop.time() + random.uniform(*self.delay_range)

    async def _warm_up_session(self, session: aiohttp.ClientSession, user_agent: str) -> None:
        session_id = id(session)
        if session_id in self._warmed_sessions:
            return
        self._warmed_sessions.add(session_id)
        try:
            async with session.get(WARMUP_URL, headers=build_warmup_headers(user_agent), timeout=aiohttp.ClientTimeout(total=10)) as response:
                await response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.debug("Async warm-up failed (non-fatal): %s", error)

    def _blocked_or_stale(self, domain, stale_payload=None, status_code=403):
        self._reset_identity()
        if stale_payload is not None:
            return self._build_provider_stale_fallback(stale_payload, status_code=status_code)
        return build_provider_blocked_result(domain)

    def _notify_rate_limit(self, status_code: int, provider_blocked: bool = False) -> None:
        try:
            self.rate_controller.on_rate_limit(status_code, provider_blocked=provider_blocked)
        except TypeError:
            self.rate_controller.on_rate_limit(status_code)

    async def health_check(self, domain=HEALTHCHECK_DOMAIN, session=None):
        """Sonde live unique avant batch pour ne pas demarrer si CloudFront bloque deja."""
        clean_domain = self._extract_domain(domain)
        cooldown_seconds = self.rate_controller.before_request()
        if cooldown_seconds > 0:
            self._reset_identity()
            return {
                "ok": False,
                "blocked": True,
                "domain": clean_domain,
                "status_code": 403,
                "error": "Circuit breaker cooldown active.",
                "cooldown_seconds": cooldown_seconds,
            }

        endpoint = API_ENDPOINT_TEMPLATE.format(domain=clean_domain)
        client_timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        owns_session = session is None
        local_session = session

        try:
            if local_session is None:
                local_session = aiohttp.ClientSession(timeout=client_timeout)
            await self._warm_up_session(local_session, self.session_user_agent)
            await self._wait_for_request_slot()

            async with local_session.get(
                endpoint,
                headers=build_request_headers(user_agent=self.session_user_agent),
                proxy=self._get_random_proxy(),
            ) as response:
                if response.status == 200:
                    await response.read()
                    self.rate_controller.on_success()
                    return {"ok": True, "blocked": False, "domain": clean_domain, "status_code": 200}

                if response.status in {403, 429}:
                    response_preview = await response.text() if response.status == 403 else ""
                    blocked = response.status == 429 or is_cloudfront_block(response.status, response.headers, response_preview)
                    self._notify_rate_limit(response.status, provider_blocked=blocked)
                    if blocked:
                        self._reset_identity()
                    return {
                        "ok": False,
                        "blocked": blocked,
                        "domain": clean_domain,
                        "status_code": response.status,
                        "error": f"Health check HTTP {response.status}",
                    }

                await response.read()
                return {
                    "ok": False,
                    "blocked": False,
                    "domain": clean_domain,
                    "status_code": response.status,
                    "error": f"Health check HTTP {response.status}",
                }
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning("Async health check failed for %s: %s", clean_domain, error)
            return {
                "ok": False,
                "blocked": False,
                "domain": clean_domain,
                "error": str(error),
            }
        finally:
            if owns_session and local_session is not None:
                await local_session.close()

    async def fetch(self, website, retry_count=DEFAULT_RETRY_COUNT, semaphore=None, session=None, use_cache=True):
        domain = self._extract_domain(website)

        if use_cache and self.cache:
            cached_data = self.cache.get(domain)
            if cached_data:
                return self._build_fresh_cache_payload(cached_data)
            stale_payload = self.cache.get(domain, allow_stale=True)
        else:
            stale_payload = None

        endpoint = API_ENDPOINT_TEMPLATE.format(domain=domain)
        sem = semaphore if semaphore else asyncio.Semaphore(1)
        owns_session = session is None
        client_timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        async with sem:
            cooldown_seconds = self.rate_controller.before_request()
            if cooldown_seconds > 0:
                logger.warning("Circuit breaker active for %.1fs before %s", cooldown_seconds, domain)
                return self._blocked_or_stale(domain, stale_payload, status_code=403)

            await self._wait_for_request_slot()
            local_session = session
            try:
                if local_session is None:
                    local_session = aiohttp.ClientSession(timeout=client_timeout)
                await self._warm_up_session(local_session, self.session_user_agent)

                for attempt in range(retry_count):
                    headers = build_request_headers(user_agent=self.session_user_agent)
                    proxy = self._get_random_proxy()

                    try:
                        async with local_session.get(endpoint, headers=headers, proxy=proxy) as response:
                            if response.status == 200:
                                data = await response.json()
                                if use_cache and self.cache:
                                    self.cache.set(domain, strip_internal_metadata(data))
                                self.rate_controller.on_success()
                                return self._build_live_payload(data)

                            if response.status == 404:
                                return {"error": "Domain not found", "domain": domain, "status_code": 404}

                            if response.status in {403, 429}:
                                response_preview = await response.text() if response.status == 403 else ""
                                provider_blocked = is_cloudfront_block(response.status, response.headers, response_preview)
                                self._notify_rate_limit(response.status, provider_blocked=provider_blocked)
                                logger.warning(
                                    "Rate limited (%s) on %s attempt=%d/%d",
                                    response.status, domain, attempt + 1, retry_count,
                                )
                                if provider_blocked:
                                    logger.warning("CloudFront provider block detected on %s", domain)
                                    return self._blocked_or_stale(domain, stale_payload, status_code=response.status)

                                retry_base = 8 if response.status == 403 else 15
                                wait_time = 2 * (2 ** attempt) + random.uniform(retry_base, retry_base + 20)
                                if attempt < retry_count - 1:
                                    await asyncio.sleep(wait_time)
                                    continue
                                if stale_payload is not None:
                                    logger.info("Serving stale cache for %s after repeated %s", domain, response.status)
                                    return self._build_stale_fallback(stale_payload)
                                return {
                                    "error": f"HTTP {response.status} after retries",
                                    "domain": domain,
                                    "status_code": response.status,
                                    ERROR_KIND_KEY: ERROR_KIND_RATE_LIMITED,
                                }

                            response.raise_for_status()
                    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
                        logger.debug("Async request error for %s attempt=%d: %s", domain, attempt + 1, error)
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 * (2 ** attempt))
                            continue
                        if stale_payload is not None:
                            return self._build_stale_fallback(stale_payload)
                        return {"error": str(error), "domain": domain}
            finally:
                if owns_session and local_session is not None:
                    await local_session.close()

        if stale_payload is not None:
            return self._build_stale_fallback(stale_payload)
        return {"error": "Max retries exceeded", "domain": domain}

    async def fetch_batch(self, domains, progress_callback=None, chunk_size=None, use_cache=True, retry_count=DEFAULT_RETRY_COUNT):
        results = {}
        total = len(domains)
        if total == 0:
            return results

        semaphore = asyncio.Semaphore(max(1, self.max_concurrency))
        client_timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        effective_chunk_size = max(1, int(chunk_size)) if chunk_size else total

        completed_count = 0
        uncached_domains = []
        if use_cache and self.cache:
            for raw_domain in domains:
                clean_domain = self._extract_domain(raw_domain)
                cached_data = self.cache.get(clean_domain)
                if cached_data:
                    results[clean_domain] = self._build_fresh_cache_payload(cached_data)
                    completed_count += 1
                    if progress_callback:
                        progress_callback(completed_count, total, clean_domain, results[clean_domain])
                else:
                    uncached_domains.append(raw_domain)
        else:
            uncached_domains = list(domains)

        if not uncached_domains:
            return results

        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            health_result = await self.health_check(session=session)

            def skipped_result(raw_domain):
                clean_domain = self._extract_domain(raw_domain)
                stale_payload = self.cache.get(clean_domain, allow_stale=True) if use_cache and self.cache else None
                if stale_payload is not None:
                    return clean_domain, self._build_provider_stale_fallback(stale_payload, status_code=403)
                return clean_domain, build_provider_blocked_result(
                    clean_domain,
                    "IP/session bloquee par Similarweb. Aucun domaine live n'a ete lance."
                    if health_result.get("blocked")
                    else "Sonde Similarweb indisponible. Le lot live est suspendu par prudence.",
                )

            if not health_result.get("ok"):
                for raw_domain in uncached_domains:
                    clean_domain, skipped_payload = skipped_result(raw_domain)
                    results[clean_domain] = skipped_payload
                    completed_count += 1
                    if progress_callback:
                        progress_callback(completed_count, total, clean_domain, skipped_payload)
                return results

            async def fetch_wrapper(raw_domain):
                clean_domain = self._extract_domain(raw_domain)
                payload = await self.fetch(
                    raw_domain,
                    retry_count=retry_count,
                    semaphore=semaphore,
                    session=session,
                    use_cache=use_cache,
                )
                return clean_domain, payload

            for start_index in range(0, len(uncached_domains), effective_chunk_size):
                chunk = uncached_domains[start_index : start_index + effective_chunk_size]
                consecutive_rate_limits = 0
                if self.rate_controller.should_abort_batch():
                    remaining_raw_domains = chunk + uncached_domains[start_index + effective_chunk_size :]
                    for raw_domain in remaining_raw_domains:
                        clean_domain, skipped_payload = skipped_result(raw_domain)
                        results[clean_domain] = skipped_payload
                        completed_count += 1
                        if progress_callback:
                            progress_callback(completed_count, total, clean_domain, skipped_payload)
                    return results

                task_map = {asyncio.create_task(fetch_wrapper(domain)): domain for domain in chunk}

                while task_map:
                    done, _ = await asyncio.wait(task_map.keys(), return_when=asyncio.FIRST_COMPLETED)
                    abort_batch = False

                    for task in done:
                        raw_domain = task_map.pop(task)
                        clean_domain = self._extract_domain(raw_domain)

                        try:
                            domain, data = await task
                        except asyncio.CancelledError:
                            continue
                        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
                            logger.debug("Task failure for %s: %s", clean_domain, error)
                            domain = clean_domain
                            data = {"error": str(error), "domain": clean_domain}

                        results[domain] = data
                        completed_count += 1
                        if progress_callback:
                            progress_callback(completed_count, total, domain, data)

                        if self._is_rate_limited(data):
                            consecutive_rate_limits += 1
                        else:
                            consecutive_rate_limits = 0

                        if consecutive_rate_limits >= self.max_consecutive_rate_limits:
                            abort_batch = True
                            break

                    if not abort_batch:
                        continue

                    remaining_raw_domains = [task_map[pending_task] for pending_task in task_map]
                    for pending_task in task_map:
                        pending_task.cancel()
                    if task_map:
                        await asyncio.gather(*task_map.keys(), return_exceptions=True)

                    remaining_raw_domains.extend(uncached_domains[start_index + effective_chunk_size :])
                    for raw_domain in remaining_raw_domains:
                        clean_domain, skipped_payload = skipped_result(raw_domain)
                        results[clean_domain] = skipped_payload
                        completed_count += 1
                        if progress_callback:
                            progress_callback(completed_count, total, clean_domain, skipped_payload)
                    return results
        return results
