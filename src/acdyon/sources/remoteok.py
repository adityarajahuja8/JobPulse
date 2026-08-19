"""RemoteOK source adapter.

Source:  https://remoteok.com/api  (public JSON feed, no auth required)
ToS:     Credit RemoteOK as source; link directly to listing URL without
         redirects. 60-second crawl delay between requests.
         See DECISIONS.md for full ToS commitments.

The first element of the /api response is a metadata dict (not a job listing)
and is skipped during parsing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from acdyon.ingestion.base import SourceAdapter, ValidationResult
from acdyon.ingestion.http_client import get_json
from acdyon.ingestion.pacing import jittered_sleep
from acdyon.ingestion.validator import ResponseValidator

log = structlog.get_logger(__name__)

_API_URL = "https://remoteok.com/api"

# RemoteOK documents a 60-second crawl delay between requests to the feed.
# We use log-normal jitter with mu=65 so the mean slightly exceeds the minimum
# while remaining naturally variable.
_CRAWL_DELAY_MU = 65.0
_CRAWL_DELAY_SIGMA = 0.3

# Required keys in every raw listing dict.
_REQUIRED_KEYS = frozenset({"id", "position", "company", "url"})


class RemoteOKAdapter(SourceAdapter):
    """Ingestion adapter for the RemoteOK public JSON feed."""

    source_id = "remoteok"
    display_name = "RemoteOK"

    def __init__(self) -> None:
        self._validator = ResponseValidator(
            source_id=self.source_id,
            min_items=1,
            required_keys=_REQUIRED_KEYS,
        )

    # ── SourceAdapter interface ───────────────────────────────────────────────

    async def fetch_raw(self) -> list[dict[str, Any]]:
        """Fetch the RemoteOK public JSON feed.

        The API returns a list where the first element is a metadata object.
        We strip it out here so validate() and parse() only see job dicts.
        """
        log.info("remoteok.fetch_raw.start", url=_API_URL)

        raw = await get_json(_API_URL)

        if not isinstance(raw, list):
            raise ValueError(f"RemoteOK API returned unexpected type: {type(raw)}")

        # First element is always a metadata dict (not a listing) — skip it.
        listings = [item for item in raw if isinstance(item, dict) and "id" in item]

        log.info("remoteok.fetch_raw.done", listing_count=len(listings))
        return listings

    def validate(self, raw: list[dict[str, Any]]) -> ValidationResult:
        return self._validator.validate_raw(raw)

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalise raw RemoteOK listing dicts into the unified schema.

        ToS: ``url`` is set directly from the API's ``url`` field —
        no redirects, no tracking wrappers (see DECISIONS.md).
        """
        docs: list[dict[str, Any]] = []

        for item in raw:
            external_id = str(item.get("id", ""))
            if not external_id:
                log.warning("remoteok.parse.missing_id", item_keys=list(item.keys()))
                continue

            # Posted-at: RemoteOK returns Unix epoch as string or int.
            posted_at: datetime | None = None
            epoch = item.get("epoch") or item.get("date")
            if epoch:
                try:
                    posted_at = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
                except (ValueError, OSError):
                    pass

            # Salary: RemoteOK provides salary_min / salary_max as strings or ints.
            def _to_int(val: Any) -> int | None:
                if val is None:
                    return None
                try:
                    return int(val)
                except (TypeError, ValueError):
                    return None

            # Direct URL — clean domain and ensure valid slug route per ToS
            raw_url = str(item.get("url") or item.get("apply_url") or "")
            if item.get("slug"):
                canonical_url = f"https://remoteok.com/remote-jobs/{item.get('slug')}"
            elif raw_url:
                canonical_url = raw_url.replace("remoteOK.com", "remoteok.com")
            else:
                canonical_url = f"https://remoteok.com/remote-jobs/{external_id}"

            doc = {
                "source": self.source_id,
                "external_id": external_id,
                "title": str(item.get("position") or ""),
                "company": str(item.get("company") or ""),
                "location": str(item.get("location") or "Worldwide / Remote"),
                # Direct URL — no redirect per ToS / DECISIONS.md
                "url": canonical_url,
                "tags": list(item.get("tags") or []),
                "salary_min": _to_int(item.get("salary_min")),
                "salary_max": _to_int(item.get("salary_max")),
                # Fields that exist in Arbeitnow but not RemoteOK — kept nullable.
                "visa_sponsorship": None,
                "four_day_week": None,
                "remote": True,  # RemoteOK is remote-only by definition
                "posted_at": posted_at,
                "raw": item,
            }
            docs.append(doc)

        log.info("remoteok.parse.done", parsed=len(docs), skipped=len(raw) - len(docs))
        return docs

    async def respect_crawl_delay(self) -> None:
        """Sleep for the RemoteOK-mandated crawl delay (log-normal ~65 s)."""
        await jittered_sleep(mu=_CRAWL_DELAY_MU, sigma=_CRAWL_DELAY_SIGMA, label="remoteok.crawl_delay")
