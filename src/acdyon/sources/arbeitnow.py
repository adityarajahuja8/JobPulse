"""Arbeitnow source adapter.

Source:  https://arbeitnow.com/api/job-board-api  (public JSON, no auth, CORS enabled)
         Documented at: https://www.arbeitnow.com/blog/job-board-api
ToS:     Credit Arbeitnow as source; link to the original listing URL.
         See DECISIONS.md for full ToS commitments.

Response shape differs meaningfully from RemoteOK (different field names,
visa/4-day-week booleans, EU focus) — the normalisation here demonstrates
that the schema layer genuinely normalises across sources, not just renames
identical fields.
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

_API_URL = "https://www.arbeitnow.com/api/job-board-api"

# Arbeitnow uses pagination — fetch at most this many pages per run to avoid
# hammering. Each page contains 15 listings by default.
_MAX_PAGES = 5
_INTER_PAGE_DELAY_MU = 3.0   # seconds (log-normal mean between pages)
_INTER_PAGE_DELAY_SIGMA = 0.4

# Required keys in every raw listing dict.
_REQUIRED_KEYS = frozenset({"slug", "title", "company_name", "url"})


class ArbeitnowAdapter(SourceAdapter):
    """Ingestion adapter for the Arbeitnow public job board API."""

    source_id = "arbeitnow"
    display_name = "Arbeitnow"

    def __init__(self, max_pages: int = _MAX_PAGES) -> None:
        self.max_pages = max_pages
        self._validator = ResponseValidator(
            source_id=self.source_id,
            min_items=1,
            required_keys=_REQUIRED_KEYS,
        )

    # ── SourceAdapter interface ───────────────────────────────────────────────

    async def fetch_raw(self) -> list[dict[str, Any]]:
        """Fetch paginated Arbeitnow listings.

        Stops at the last page reported by the API or at ``max_pages``,
        whichever comes first. Jittered delay between pages.
        """
        all_listings: list[dict[str, Any]] = []

        for page in range(1, self.max_pages + 1):
            log.info("arbeitnow.fetch_raw.page", page=page, url=_API_URL)
            response = await get_json(_API_URL, params={"page": page})

            if not isinstance(response, dict):
                log.warning("arbeitnow.fetch_raw.unexpected_type", page=page)
                break

            page_data = response.get("data", [])
            if not page_data:
                log.info("arbeitnow.fetch_raw.no_more_pages", stopped_at_page=page)
                break

            all_listings.extend(page_data)

            # Check if there is a next page.
            links = response.get("links", {})
            if not links.get("next"):
                log.info("arbeitnow.fetch_raw.last_page", page=page)
                break

            # Jittered pacing between pages — never hammer pagination.
            if page < self.max_pages:
                await jittered_sleep(
                    mu=_INTER_PAGE_DELAY_MU,
                    sigma=_INTER_PAGE_DELAY_SIGMA,
                    label="arbeitnow.inter_page",
                )

        log.info("arbeitnow.fetch_raw.done", total_listings=len(all_listings))
        return all_listings

    def validate(self, raw: list[dict[str, Any]]) -> ValidationResult:
        return self._validator.validate_raw(raw)

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalise raw Arbeitnow listing dicts into the unified schema.

        Arbeitnow-specific fields (visa_sponsorship, four_day_week) are
        preserved in the unified schema as nullable booleans — RemoteOK
        docs carry None for these fields, Arbeitnow docs carry True/False.
        This is what "genuine normalisation across sources" looks like.
        """
        docs: list[dict[str, Any]] = []

        for item in raw:
            external_id = str(item.get("slug") or "")
            if not external_id:
                log.warning("arbeitnow.parse.missing_slug", item_keys=list(item.keys()))
                continue

            # Posted-at: Arbeitnow provides Unix epoch as int in "created_at".
            posted_at: datetime | None = None
            epoch = item.get("created_at")
            if epoch:
                try:
                    posted_at = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
                except (ValueError, OSError):
                    pass

            doc = {
                "source": self.source_id,
                "external_id": external_id,
                "title": str(item.get("title") or ""),
                "company": str(item.get("company_name") or ""),
                "location": str(item.get("location") or ""),
                "url": str(item.get("url") or ""),
                "tags": list(item.get("tags") or []),
                # RemoteOK-style salary fields don't exist in Arbeitnow — nullable.
                "salary_min": None,
                "salary_max": None,
                # Arbeitnow-specific booleans — absent from RemoteOK (None there).
                "visa_sponsorship": bool(item.get("visa_sponsorship", False)),
                "four_day_week": bool(item.get("four_day_week", False)),
                "remote": bool(item.get("remote", False)),
                "posted_at": posted_at,
                "raw": item,
            }
            docs.append(doc)

        log.info("arbeitnow.parse.done", parsed=len(docs), skipped=len(raw) - len(docs))
        return docs
