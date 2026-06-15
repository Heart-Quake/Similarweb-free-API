"""Script CLI pour verifier le bon fonctionnement du client async + cache.

Usage: python3 verify_async.py
"""
import asyncio
import os
import time

from cache import SQLiteCache
from config import get_logger
from core_async import AsyncSimilarClient

logger = get_logger("verify")


async def main():
    logger.info("Starting verification script")

    cache = SQLiteCache(db_path="verify_cache.db")
    client = AsyncSimilarClient(cache=cache)

    domains = [
        "google.com",
        "wikipedia.org",
        "github.com",
        "stackoverflow.com",
        "python.org",
        "haseundco.de",
    ]

    logger.info("Test 1: single fetch (google.com)")
    started = time.time()
    data = await client.fetch("google.com")
    logger.info(
        "  result=%s elapsed=%.2fs",
        "ok" if isinstance(data, dict) and "EstimatedMonthlyVisits" in data else "ko",
        time.time() - started,
    )

    logger.info("Test 2: batch fetch (%d domains)", len(domains))
    started = time.time()
    results = await client.fetch_batch(domains)
    successes = sum(1 for payload in results.values() if isinstance(payload, dict) and "SiteName" in payload)
    logger.info("  success=%d/%d elapsed=%.2fs", successes, len(domains), time.time() - started)

    logger.info("Test 3: cache replay")
    started = time.time()
    await client.fetch_batch(domains)
    logger.info("  elapsed=%.2fs (should be near-zero)", time.time() - started)

    if os.path.exists("verify_cache.db"):
        logger.info("SQLite DB present: verify_cache.db")
    else:
        logger.error("SQLite DB missing")

    logger.info("Verification complete")


if __name__ == "__main__":
    asyncio.run(main())
