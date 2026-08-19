"""Async httpx client factory.

Produces a pre-configured AsyncClient with:
- An honest User-Agent identifying this bot (per DESIGN.md §4 and DECISIONS.md).
- Optional proxy routing (reads PROXY_URL from settings; blank = no proxy).
- Sensible timeouts and HTTP/2 enabled.

Usage:
    async with build_client() as client:
        response = await client.get(url)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx

from acdyon.config import settings

# Honest bot User-Agent per DECISIONS.md.
# If you have a public project URL, replace the placeholder.
_USER_AGENT = (
    "acdyon-ingestion/0.1 "
    "(ethical job-data pipeline; contact: your-email@example.com)"
)

_DEFAULT_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "application/json, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@asynccontextmanager
async def build_client(
    *,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    follow_redirects: bool = True,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async context manager that yields a configured httpx.AsyncClient.

    Args:
        headers:          Extra headers to merge with defaults.
        timeout:          Override request timeout (seconds).
        follow_redirects: Whether to follow HTTP redirects.
    """
    merged_headers = {**_DEFAULT_HEADERS, **(headers or {})}
    proxy: str | None = settings.proxy_url or None

    client_kwargs: dict = dict(
        headers=merged_headers,
        timeout=httpx.Timeout(timeout or settings.http_timeout_seconds),
        follow_redirects=follow_redirects,
        http2=True,
    )
    if proxy:
        client_kwargs["proxy"] = proxy

    async with httpx.AsyncClient(**client_kwargs) as client:
        yield client


async def get_json(
    url: str,
    *,
    params: dict | None = None,
    extra_headers: dict[str, str] | None = None,
    retries: int | None = None,
) -> list | dict:
    """Fetch a URL and return parsed JSON.

    Retries up to ``retries`` times (default: settings.http_max_retries) on
    transient errors (connection error, 5xx status). Raises ``httpx.HTTPError``
    on final failure.
    """
    max_attempts = (retries if retries is not None else settings.http_max_retries) + 1
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            async with build_client(headers=extra_headers) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt < max_attempts:
                # Let the caller's pacing layer control inter-retry delay.
                continue

    raise last_exc  # type: ignore[misc]
