"""JSearch (RapidAPI) source adapter.

Source:   https://jsearch.p.rapidapi.com/search-v2
Provider: RapidAPI (Let's Scrape)
Auth:     x-rapidapi-key, x-rapidapi-host

Fetches structured job listings across major tech aggregators via JSearch API v2.
Maps into the unified Acdyon schema with direct apply URLs, structured salary,
and location data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from acdyon.config import settings
from acdyon.ingestion.base import SourceAdapter, ValidationResult
from acdyon.ingestion.http_client import build_client
from acdyon.ingestion.validator import ResponseValidator

log = structlog.get_logger(__name__)

_API_URL = "https://jsearch.p.rapidapi.com/search-v2"

# Required keys in raw JSearch listing objects
_REQUIRED_KEYS = frozenset({"job_id", "job_title", "job_apply_link"})


# ── Natural Language Search Query Parser ──────────────────────────────────────

# ISO 3166-1 alpha-2 country mappings for common natural language names
_COUNTRY_MAP: dict[str, str] = {
    "india": "in",
    "in": "in",
    "united states": "us",
    "usa": "us",
    "us": "us",
    "america": "us",
    "united kingdom": "gb",
    "uk": "gb",
    "great britain": "gb",
    "canada": "ca",
    "germany": "de",
    "deutschland": "de",
    "france": "fr",
    "australia": "au",
    "singapore": "sg",
    "netherlands": "nl",
    "japan": "jp",
    "brazil": "br",
}


_UNSET = object()


def parse_search_prompt(user_prompt: str | None) -> dict[str, Any]:
    """Parse a natural-language search request into clean, structured JSearch parameters.

    Rules:
    1. Extracts 'role' / keywords as pure title string — never appends location into it.
    2. Extracts 'country' as separate 2-letter ISO code if specified.
    3. Extracts 'location' as separate city/region string if specified.
    4. If the user doesn't specify a role, leaves 'role' unset (None) rather than assuming one.
    5. If the user doesn't specify a location/country, leaves 'country' unset (None) rather than assuming 'us'.
    6. Extracts 'remote_only' boolean flag.

    Example inputs:
        - "Find data analyst jobs in India" -> {'role': 'data analyst', 'country': 'in', 'location': None, 'remote_only': False}
        - "Remote python developer in Texas" -> {'role': 'python developer', 'country': 'us', 'location': 'Texas', 'remote_only': True}
        - "" (empty) -> {'role': None, 'country': None, 'location': None, 'remote_only': False}
    """
    if not user_prompt or not user_prompt.strip():
        return {
            "role": None,
            "country": None,
            "location": None,
            "remote_only": False,
        }

    text = user_prompt.strip()
    remote_only = bool(
        "remote" in text.lower() or "wfh" in text.lower() or "work from home" in text.lower()
    )

    # Clean leading search intent prefixes
    cleaned = text
    for prefix in [
        "find",
        "search for",
        "search",
        "looking for",
        "show me",
        "get",
        "list",
    ]:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
            break

    country: str | None = None
    location: str | None = None
    role: str | None = cleaned

    # Check for " in <location/country>" pattern
    if " in " in cleaned.lower():
        parts = cleaned.split(" in ", 1)
        role_candidate = parts[0].strip()
        loc_candidate = parts[1].strip()

        # Check if loc_candidate matches a known country
        loc_lower = loc_candidate.lower()
        if loc_lower in _COUNTRY_MAP:
            country = _COUNTRY_MAP[loc_lower]
            location = None
        else:
            # e.g. "Texas, USA" or "Bangalore, India" or "Austin"
            if "," in loc_candidate:
                sub_parts = [p.strip() for p in loc_candidate.split(",", 1)]
                location = sub_parts[0]
                if sub_parts[1].lower() in _COUNTRY_MAP:
                    country = _COUNTRY_MAP[sub_parts[1].lower()]
            else:
                location = loc_candidate

        role = role_candidate if role_candidate else None

    # Strip suffix filler words like "jobs", "positions", "openings", "roles"
    if role:
        for suffix in [
            "jobs",
            "job",
            "positions",
            "position",
            "openings",
            "opening",
            "roles",
            "role",
        ]:
            if role.lower().endswith(suffix):
                role = role[: -len(suffix)].strip()

    # Strip "remote" keyword from role string so query text is pure role
    if role:
        role_clean = (
            role.replace("remote", "").replace("Remote", "").replace("REMOTE", "").strip()
        )
        role = role_clean if role_clean else None

    return {
        "role": role,
        "country": country,
        "location": location,
        "remote_only": remote_only,
    }


class JSearchAdapter(SourceAdapter):
    """Role-agnostic and country-agnostic adapter for the JSearch (RapidAPI) search-v2 endpoint."""

    source_id = "jsearch"
    display_name = "JSearch (RapidAPI)"

    def __init__(
        self,
        role: str | None = None,
        country: Any = _UNSET,
        location: str | None = None,
        remote_only: bool = False,
        page: int = 1,
        num_pages: int = 1,
        date_posted: str = "all",
    ) -> None:
        """Initialize JSearch adapter with decoupled role, country, and location parameters.

        Args:
            role: Free-text job title/keyword (e.g. "data analyst", "frontend engineer").
                  Defaults to settings.jsearch_default_role if None.
            country: 2-letter ISO country code (e.g. "us", "in", "gb").
                     Defaults to settings.jsearch_default_country if omitted. Pass None for country-agnostic global search.
            location: Specific city/state (e.g. "Austin", "Bangalore"). Never concatenated into query.
            remote_only: If True, sets work_from_home="true".
            page: Starting page number for pagination (1-indexed).
            num_pages: Number of pages to retrieve via cursor pagination (default: 1).
            date_posted: Posting freshness filter ('all', 'today', '3days', 'week', 'month').
        """
        self.role = role.strip() if role else settings.jsearch_default_role

        if country is _UNSET:
            self.country = settings.jsearch_default_country
        elif country is None:
            self.country = None
        else:
            self.country = str(country).lower().strip()

        self.location = location.strip() if location else settings.jsearch_default_location
        self.remote_only = remote_only
        self.page = max(1, page)
        self.num_pages = max(1, num_pages)
        self.date_posted = date_posted

        self._validator = ResponseValidator(
            source_id=self.source_id,
            min_items=1,
            required_keys=_REQUIRED_KEYS,
        )

    def build_request_params(self, cursor: str | None = None) -> dict[str, Any]:
        """Construct the exact query parameters dictionary sent to JSearch /search-v2.

        Guarantees:
        1. 'query' parameter contains ONLY the role/keywords — NEVER location/country text.
        2. 'country' is passed exclusively via the dedicated 'country' parameter.
        3. 'location' is passed exclusively via the dedicated 'location' parameter if present.
        4. 'work_from_home' is set to 'true' when remote_only is True.
        5. 'cursor' is passed when paginating through multiple batches.
        """
        params: dict[str, Any] = {
            "query": self.role,
            "num_pages": str(self.num_pages),
            "date_posted": self.date_posted,
        }

        # Dedicated separate country parameter
        if self.country:
            params["country"] = self.country

        # Dedicated separate location parameter (if supplied)
        if self.location:
            params["location"] = self.location

        # Dedicated remote parameter per search-v2 API
        if self.remote_only:
            params["work_from_home"] = "true"

        if cursor:
            params["cursor"] = cursor

        return params

    # ── SourceAdapter interface ───────────────────────────────────────────────

    async def fetch_raw(self) -> list[dict[str, Any]]:
        """Fetch listings exclusively from JSearch RapidAPI /search-v2 endpoint with cursor pagination.

        Guarantees:
        - Calls ONLY GET https://jsearch.p.rapidapi.com/search-v2
        - Supports cursor-based multi-page pagination when num_pages > 1
        - Preserves all valid jobs returned by JSearch
        - Never uses hardcoded job_id or fallback to static/fake jobs
        - Logs detailed HTTP/API diagnostics on success or failure without exposing the API key
        """
        base_params = self.build_request_params()
        log.info(
            "jsearch.fetch_raw.start",
            endpoint=_API_URL,
            params=base_params,
            role=self.role,
            country=self.country,
            location=self.location,
            remote_only=self.remote_only,
            num_pages=self.num_pages,
        )

        if not settings.rapidapi_key or settings.rapidapi_key == "your_rapidapi_key_here":
            log.warning(
                "jsearch.fetch_raw.no_api_key",
                message="RapidAPI key is not configured. Set RAPIDAPI_KEY in .env or environment.",
            )
            return []

        headers = {
            "x-rapidapi-key": settings.rapidapi_key,
            "x-rapidapi-host": settings.rapidapi_host,
            "Content-Type": "application/json",
        }

        all_listings: list[dict[str, Any]] = []
        seen_job_ids: set[str] = set()
        cursor: str | None = None

        async with build_client(headers=headers) as client:
            for page_idx in range(1, self.num_pages + 1):
                req_params = self.build_request_params(cursor=cursor)
                try:
                    response = await client.get(_API_URL, params=req_params)
                    status_code = response.status_code

                    if status_code != 200:
                        log.error(
                            "jsearch.fetch_raw.http_error",
                            endpoint=_API_URL,
                            params=req_params,
                            status_code=status_code,
                            error_body=response.text[:500],
                        )
                        break

                    payload = response.json()
                    data_obj = payload.get("data") if isinstance(payload, dict) else payload

                    batch_jobs: list[dict[str, Any]] = []
                    next_cursor: str | None = None

                    if isinstance(data_obj, dict):
                        batch_jobs = data_obj.get("jobs", [])
                        next_cursor = data_obj.get("cursor")
                    elif isinstance(data_obj, list):
                        batch_jobs = data_obj

                    if not batch_jobs:
                        log.info(
                            "jsearch.fetch_raw.empty_batch",
                            endpoint=_API_URL,
                            page_idx=page_idx,
                            total_so_far=len(all_listings),
                        )
                        break

                    # Append unique jobs from this batch
                    new_in_batch = 0
                    for j in batch_jobs:
                        jid = str(j.get("job_id") or "")
                        if jid and jid not in seen_job_ids:
                            seen_job_ids.add(jid)
                            all_listings.append(j)
                            new_in_batch += 1
                        elif not jid:
                            all_listings.append(j)
                            new_in_batch += 1

                    log.info(
                        "jsearch.fetch_raw.batch_done",
                        endpoint=_API_URL,
                        page_idx=page_idx,
                        batch_received=len(batch_jobs),
                        new_added=new_in_batch,
                        total_accumulated=len(all_listings),
                        has_next_cursor=bool(next_cursor),
                    )

                    # If no more cursor or we reached requested page count, stop
                    if not next_cursor or page_idx >= self.num_pages:
                        break

                    cursor = next_cursor

                except httpx.HTTPStatusError as exc:
                    log.error(
                        "jsearch.fetch_raw.http_status_error",
                        endpoint=_API_URL,
                        params=req_params,
                        status_code=exc.response.status_code if exc.response else None,
                        error=str(exc),
                    )
                    break
                except httpx.RequestError as exc:
                    log.error(
                        "jsearch.fetch_raw.request_error",
                        endpoint=_API_URL,
                        params=req_params,
                        error=str(exc),
                    )
                    break
                except Exception as exc:
                    log.error(
                        "jsearch.fetch_raw.unexpected_error",
                        endpoint=_API_URL,
                        params=req_params,
                        error=str(exc),
                    )
                    break

        log.info(
            "jsearch.fetch_raw.done",
            endpoint=_API_URL,
            total_jobs_returned=len(all_listings),
            pages_fetched=self.num_pages,
        )
        return all_listings

    def validate(self, raw: list[dict[str, Any]]) -> ValidationResult:
        return self._validator.validate_raw(raw)

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalise raw JSearch listing dicts into the unified MongoDB schema."""
        docs: list[dict[str, Any]] = []

        for item in raw:
            external_id = str(item.get("job_id") or "")
            if not external_id:
                log.warning("jsearch.parse.missing_job_id", keys=list(item.keys()))
                continue

            # Parse posted_at timestamp or ISO UTC string
            posted_at: datetime | None = None
            date_utc = item.get("job_posted_at_datetime_utc")
            ts = item.get("job_posted_at_timestamp")

            if date_utc:
                try:
                    clean_iso = date_utc.replace("Z", "+00:00")
                    posted_at = datetime.fromisoformat(clean_iso)
                except (ValueError, TypeError):
                    pass
            elif ts:
                try:
                    posted_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                except (ValueError, OSError):
                    pass

            # Construct readable location
            location = item.get("job_location") or ""
            if not location:
                city = item.get("job_city") or ""
                state = item.get("job_state") or ""
                country = item.get("job_country") or ""
                location_parts = [p for p in [city, state, country] if p]
                location = ", ".join(location_parts) if location_parts else "Worldwide / Remote"

            # Parse salary bounds
            def _to_int(val: Any) -> int | None:
                if val is None or val == 0:
                    return None
                try:
                    return int(float(val))
                except (TypeError, ValueError):
                    return None

            # Collect tags & skills from required_technologies, preferred_technologies, or skills
            tags: list[str] = []
            for field_name in ("required_technologies", "preferred_technologies", "job_required_skills"):
                field_vals = item.get(field_name)
                if isinstance(field_vals, list):
                    tags.extend([str(s).lower() for s in field_vals if s])

            job_fn = item.get("job_function")
            if job_fn and str(job_fn).lower() not in tags:
                tags.append(str(job_fn).lower())

            emp_type = item.get("job_employment_type")
            if emp_type and str(emp_type).lower() not in tags:
                tags.append(str(emp_type).lower())

            # Deduplicate tags
            tags = list(dict.fromkeys(tags))[:8]

            doc = {
                "source": self.source_id,
                "external_id": external_id,
                "title": str(item.get("job_title") or ""),
                "company": str(item.get("employer_name") or ""),
                "location": location,
                "url": str(item.get("job_apply_link") or ""),
                "tags": tags,
                "salary_min": _to_int(item.get("job_min_salary")),
                "salary_max": _to_int(item.get("job_max_salary")),
                "visa_sponsorship": None,
                "four_day_week": None,
                "remote": bool(item.get("job_is_remote", False) or item.get("work_arrangement") == "remote"),
                "posted_at": posted_at,
                "raw": item,
            }
            docs.append(doc)

        log.info("jsearch.parse.done", parsed=len(docs), skipped=len(raw) - len(docs))
        return docs
