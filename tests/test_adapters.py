"""Unit tests for source adapters.

Network is fully mocked via respx — no real HTTP calls.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import respx
from httpx import Response

from tests.conftest import JSEARCH_FIXTURE, REMOTEOK_FIXTURE
from acdyon.config import settings
from acdyon.sources.remoteok import RemoteOKAdapter
from acdyon.sources.jsearch import JSearchAdapter


# ── RemoteOK adapter tests ────────────────────────────────────────────────────


class TestRemoteOKAdapter:
    """Tests for RemoteOKAdapter parsing and validation."""

    @pytest.fixture
    def adapter(self):
        return RemoteOKAdapter()

    # ── validate ──────────────────────────────────────────────────────────────

    def test_validate_ok_with_valid_listings(self, adapter):
        # Exclude the metadata first element.
        listings = [item for item in REMOTEOK_FIXTURE if "id" in item]
        result = adapter.validate(listings)
        assert result.ok is True

    def test_validate_fails_on_empty(self, adapter):
        result = adapter.validate([])
        assert result.ok is False

    # ── parse ─────────────────────────────────────────────────────────────────

    def test_parse_returns_correct_count(self, adapter):
        raw = [item for item in REMOTEOK_FIXTURE if "id" in item]
        docs = adapter.parse(raw)
        assert len(docs) == 2

    def test_parse_normalised_schema_fields(self, adapter):
        raw = [item for item in REMOTEOK_FIXTURE if "id" in item]
        doc = adapter.parse(raw)[0]

        assert doc["source"] == "remoteok"
        assert doc["external_id"] == "12345"
        assert doc["title"] == "Senior Python Engineer"
        assert doc["company"] == "Acme Corp"
        assert doc["location"] == "Worldwide"
        assert doc["url"] == "https://remoteok.com/remote-jobs/12345"
        assert "python" in doc["tags"]
        assert doc["salary_min"] == 100000
        assert doc["salary_max"] == 140000
        # RemoteOK-specific nullable fields.
        assert doc["visa_sponsorship"] is None
        assert doc["four_day_week"] is None
        assert doc["remote"] is True

    def test_parse_posted_at_is_datetime(self, adapter):
        raw = [item for item in REMOTEOK_FIXTURE if "id" in item]
        doc = adapter.parse(raw)[0]
        assert isinstance(doc["posted_at"], datetime)
        assert doc["posted_at"].tzinfo is not None   # timezone-aware

    def test_parse_url_is_direct_no_redirect(self, adapter):
        """URL must be the direct RemoteOK URL — no tracking wrappers per ToS."""
        raw = [item for item in REMOTEOK_FIXTURE if "id" in item]
        for doc in adapter.parse(raw):
            assert doc["url"].startswith("https://remoteok.com/"), (
                f"URL must point directly to remoteok.com, got: {doc['url']}"
            )

    def test_parse_skips_items_without_id(self, adapter):
        raw = [{"position": "No ID", "company": "X", "url": "https://x.com"}]
        docs = adapter.parse(raw)
        assert len(docs) == 0

    def test_parse_preserves_raw(self, adapter):
        raw = [item for item in REMOTEOK_FIXTURE if "id" in item]
        doc = adapter.parse(raw)[0]
        assert "raw" in doc
        assert doc["raw"]["id"] == "12345"

    def test_validate_against_parsed_output(self, adapter):
        """validate() should pass on the same data that parse() will process."""
        raw = [item for item in REMOTEOK_FIXTURE if "id" in item]
        assert adapter.validate(raw).ok is True

    @respx.mock
    async def test_fetch_raw_strips_metadata_element(self, adapter, respx_mock):
        """fetch_raw() should strip the first metadata element."""
        import json
        respx_mock.get("https://remoteok.com/api").mock(
            return_value=Response(200, json=REMOTEOK_FIXTURE)
        )
        raw = await adapter.fetch_raw()
        # Metadata element (no "id") should be excluded.
        assert all("id" in item for item in raw)
        assert len(raw) == 2


# ── JSearch (RapidAPI) adapter tests ──────────────────────────────────────────


class TestJSearchAdapter:
    """Tests for JSearchAdapter parsing and validation."""

    @pytest.fixture
    def adapter(self):
        return JSearchAdapter()

    # ── validate ──────────────────────────────────────────────────────────────

    def test_validate_ok_with_valid_listings(self, adapter):
        result = adapter.validate(JSEARCH_FIXTURE["data"])
        assert result.ok is True

    def test_validate_fails_on_empty(self, adapter):
        result = adapter.validate([])
        assert result.ok is False

    # ── parse ─────────────────────────────────────────────────────────────────

    def test_parse_returns_correct_count(self, adapter):
        docs = adapter.parse(JSEARCH_FIXTURE["data"])
        assert len(docs) == 2

    def test_parse_normalised_schema_fields(self, adapter):
        doc = adapter.parse(JSEARCH_FIXTURE["data"])[0]

        assert doc["source"] == "jsearch"
        assert doc["external_id"] == "google-swe-12345"
        assert doc["title"] == "Senior Cloud Infrastructure Engineer"
        assert doc["company"] == "Google"
        assert "Mountain View" in doc["location"]
        assert doc["url"] == "https://careers.google.com/jobs/results/12345"
        assert "python" in doc["tags"]
        assert doc["salary_min"] == 180000
        assert doc["salary_max"] == 250000
        assert doc["remote"] is True

    def test_parse_posted_at_is_datetime(self, adapter):
        doc = adapter.parse(JSEARCH_FIXTURE["data"])[0]
        assert isinstance(doc["posted_at"], datetime)
        assert doc["posted_at"].tzinfo is not None

    def test_parse_skips_items_without_job_id(self, adapter):
        raw = [{"job_title": "No ID", "employer_name": "X", "job_apply_link": "https://x.com"}]
        docs = adapter.parse(raw)
        assert len(docs) == 0

    def test_parse_preserves_raw(self, adapter):
        doc = adapter.parse(JSEARCH_FIXTURE["data"])[0]
        assert "raw" in doc
        assert doc["raw"]["job_id"] == "google-swe-12345"

    # ── Decoupled parameters & request construction tests ────────────────────

    def test_build_request_params_role_and_country_specified(self):
        """query must contain ONLY the role; country and location are separate params."""
        adapter = JSearchAdapter(role="data analyst", country="in")
        params = adapter.build_request_params()

        assert params["query"] == "data analyst"
        assert "in" not in params["query"]  # Location NOT merged into query
        assert params["country"] == "in"
        assert "location" not in params

    def test_build_request_params_with_location_specified(self):
        """location must be passed exclusively as its own parameter, and work_from_home for remote."""
        adapter = JSearchAdapter(role="python developer", country="us", location="Texas", remote_only=True)
        params = adapter.build_request_params()

        assert params["query"] == "python developer"
        assert "Texas" not in params["query"]
        assert "in" not in params["query"]
        assert params["country"] == "us"
        assert params["location"] == "Texas"
        assert params["work_from_home"] == "true"

    def test_build_request_params_country_agnostic_when_none(self):
        """When country is explicitly None, it should not send a country param."""
        adapter = JSearchAdapter(role="Staff DevOps", country=None)
        params = adapter.build_request_params()

        assert params["query"] == "Staff DevOps"
        assert "country" not in params

    def test_build_request_params_defaults_when_unspecified(self):
        """When neither is specified, use clearly documented app-wide defaults."""
        adapter = JSearchAdapter()
        params = adapter.build_request_params()

        assert params["query"] == settings.jsearch_default_role
        assert params["country"] == settings.jsearch_default_country

    # ── Natural language prompt parsing tests ────────────────────────────────

    def test_parse_search_prompt_with_role_and_country(self):
        from acdyon.sources.jsearch import parse_search_prompt

        res = parse_search_prompt("Find data analyst jobs in India")
        assert res["role"] == "data analyst"
        assert res["country"] == "in"
        assert res["location"] is None
        assert res["remote_only"] is False

    def test_parse_search_prompt_with_remote_and_location(self):
        from acdyon.sources.jsearch import parse_search_prompt

        res = parse_search_prompt("Remote python developer in Texas, USA")
        assert res["role"] == "python developer"
        assert res["country"] == "us"
        assert res["location"] == "Texas"
        assert res["remote_only"] is True

    def test_parse_search_prompt_unspecified_leaves_fields_unset(self):
        from acdyon.sources.jsearch import parse_search_prompt

        res = parse_search_prompt("")
        assert res["role"] is None
        assert res["country"] is None
        assert res["location"] is None

    # ── Fetch raw with search-v2 endpoint & error handling tests ─────────────

    def test_total_jobs_validation_fails_on_zero_or_negative(self):
        """total_jobs < 1 must raise ValueError."""
        import pytest

        with pytest.raises(ValueError, match="total_jobs must be >= 1"):
            JSearchAdapter(total_jobs=0)

        with pytest.raises(ValueError, match="total_jobs must be >= 1"):
            JSearchAdapter(total_jobs=-5)

    @respx.mock
    async def test_total_jobs_10_single_request(self, respx_mock):
        """total_jobs=10 fetches a single batch of 10 jobs."""
        adapter = JSearchAdapter(role="software engineer", total_jobs=10)

        jobs_batch = [
            {"job_id": f"job-{i}", "job_title": f"Engineer {i}", "job_apply_link": f"https://example.com/{i}"}
            for i in range(10)
        ]
        respx_mock.get("https://jsearch.p.rapidapi.com/search-v2").mock(
            return_value=Response(200, json={"status": "OK", "data": {"jobs": jobs_batch, "cursor": "cur-1"}})
        )

        results = await adapter.fetch_raw()
        assert len(results) == 10
        assert len(respx_mock.calls) == 1

    @respx.mock
    async def test_total_jobs_20_multi_batch_cursor_pagination(self, respx_mock):
        """total_jobs=20 makes 2 requests with cursor and returns 20 unique jobs."""
        adapter = JSearchAdapter(role="software engineer", total_jobs=20)

        batch1 = [
            {"job_id": f"job-{i}", "job_title": f"Engineer {i}", "job_apply_link": f"https://example.com/{i}"}
            for i in range(10)
        ]
        batch2 = [
            {"job_id": f"job-{i}", "job_title": f"Engineer {i}", "job_apply_link": f"https://example.com/{i}"}
            for i in range(10, 20)
        ]

        route = respx_mock.get("https://jsearch.p.rapidapi.com/search-v2")
        route.side_effect = [
            Response(200, json={"status": "OK", "data": {"jobs": batch1, "cursor": "cur-2"}}),
            Response(200, json={"status": "OK", "data": {"jobs": batch2, "cursor": "cur-3"}}),
        ]

        results = await adapter.fetch_raw()
        assert len(results) == 20
        assert len(respx_mock.calls) == 2
        assert "cursor" not in respx_mock.calls[0].request.url.params
        assert respx_mock.calls[1].request.url.params["cursor"] == "cur-2"

    @respx.mock
    async def test_total_jobs_50_multi_batch_cursor_pagination(self, respx_mock):
        """total_jobs=50 makes 5 requests with cursor and returns 50 unique jobs."""
        adapter = JSearchAdapter(role="software engineer", total_jobs=50)

        batches = []
        for b in range(5):
            batches.append([
                {"job_id": f"job-{b}-{i}", "job_title": f"Engineer {b}-{i}", "job_apply_link": f"https://example.com/{b}-{i}"}
                for i in range(10)
            ])

        route = respx_mock.get("https://jsearch.p.rapidapi.com/search-v2")
        route.side_effect = [
            Response(200, json={"status": "OK", "data": {"jobs": batches[0], "cursor": "c1"}}),
            Response(200, json={"status": "OK", "data": {"jobs": batches[1], "cursor": "c2"}}),
            Response(200, json={"status": "OK", "data": {"jobs": batches[2], "cursor": "c3"}}),
            Response(200, json={"status": "OK", "data": {"jobs": batches[3], "cursor": "c4"}}),
            Response(200, json={"status": "OK", "data": {"jobs": batches[4], "cursor": "c5"}}),
        ]

        results = await adapter.fetch_raw()
        assert len(results) == 50
        assert len(respx_mock.calls) == 5

    @respx.mock
    async def test_api_returns_fewer_jobs_than_requested(self, respx_mock):
        """When API runs out of jobs (e.g. 15 available), return 15 without fabricating more."""
        adapter = JSearchAdapter(role="specialist", total_jobs=50)

        batch1 = [
            {"job_id": f"job-{i}", "job_title": f"Specialist {i}", "job_apply_link": f"https://example.com/{i}"}
            for i in range(10)
        ]
        batch2 = [
            {"job_id": f"job-{i}", "job_title": f"Specialist {i}", "job_apply_link": f"https://example.com/{i}"}
            for i in range(10, 15)
        ]

        route = respx_mock.get("https://jsearch.p.rapidapi.com/search-v2")
        route.side_effect = [
            Response(200, json={"status": "OK", "data": {"jobs": batch1, "cursor": "c1"}}),
            Response(200, json={"status": "OK", "data": {"jobs": batch2, "cursor": None}}),  # No more cursor
        ]

        results = await adapter.fetch_raw()
        assert len(results) == 15
        assert len(respx_mock.calls) == 2

    @respx.mock
    async def test_duplicate_jobs_across_cursor_batches_deduplicated(self, respx_mock):
        """Duplicate jobs across cursor batches must be deduplicated by job_id."""
        adapter = JSearchAdapter(role="dev", total_jobs=15)

        batch1 = [
            {"job_id": f"job-{i}", "job_title": f"Dev {i}", "job_apply_link": "https://ex.com"}
            for i in range(10)
        ]
        # Batch 2 has 5 duplicate jobs from batch 1 and 5 new jobs
        batch2 = [
            {"job_id": f"job-{i}", "job_title": f"Dev {i}", "job_apply_link": "https://ex.com"}
            for i in range(5, 15)
        ]

        route = respx_mock.get("https://jsearch.p.rapidapi.com/search-v2")
        route.side_effect = [
            Response(200, json={"status": "OK", "data": {"jobs": batch1, "cursor": "c1"}}),
            Response(200, json={"status": "OK", "data": {"jobs": batch2, "cursor": "c2"}}),
        ]

        results = await adapter.fetch_raw()
        assert len(results) == 15
        unique_ids = {r["job_id"] for r in results}
        assert len(unique_ids) == 15

    @respx.mock
    async def test_missing_cursor_stops_pagination(self, respx_mock):
        """If cursor is None/missing in response, pagination terminates cleanly."""
        adapter = JSearchAdapter(total_jobs=30)

        batch1 = [
            {"job_id": f"job-{i}", "job_title": f"Dev {i}", "job_apply_link": "https://ex.com"}
            for i in range(10)
        ]
        respx_mock.get("https://jsearch.p.rapidapi.com/search-v2").mock(
            return_value=Response(200, json={"status": "OK", "data": {"jobs": batch1, "cursor": None}})
        )

        results = await adapter.fetch_raw()
        assert len(results) == 10
        assert len(respx_mock.calls) == 1

    @respx.mock
    async def test_api_error_stops_pagination_safely(self, respx_mock):
        """If second request returns 500/404, return accumulated results without crashing."""
        adapter = JSearchAdapter(total_jobs=30)

        batch1 = [
            {"job_id": f"job-{i}", "job_title": f"Dev {i}", "job_apply_link": "https://ex.com"}
            for i in range(10)
        ]

        route = respx_mock.get("https://jsearch.p.rapidapi.com/search-v2")
        route.side_effect = [
            Response(200, json={"status": "OK", "data": {"jobs": batch1, "cursor": "c1"}}),
            Response(500, json={"message": "Internal error"}),
        ]

        results = await adapter.fetch_raw()
        assert len(results) == 10
        assert len(respx_mock.calls) == 2

    @respx.mock
    async def test_empty_batch_stops_pagination(self, respx_mock):
        """If a batch returns empty list, stop pagination."""
        adapter = JSearchAdapter(total_jobs=30)

        route = respx_mock.get("https://jsearch.p.rapidapi.com/search-v2")
        route.side_effect = [
            Response(200, json={"status": "OK", "data": {"jobs": [], "cursor": "c1"}}),
        ]

        results = await adapter.fetch_raw()
        assert results == []
        assert len(respx_mock.calls) == 1

    @respx.mock
    async def test_requested_total_is_never_exceeded(self, respx_mock):
        """When API returns 10 jobs per batch and total_jobs=12, only 12 jobs are returned."""
        adapter = JSearchAdapter(total_jobs=12)

        batch1 = [
            {"job_id": f"job-{i}", "job_title": f"Dev {i}", "job_apply_link": "https://ex.com"}
            for i in range(10)
        ]
        batch2 = [
            {"job_id": f"job-{i}", "job_title": f"Dev {i}", "job_apply_link": "https://ex.com"}
            for i in range(10, 20)
        ]

        route = respx_mock.get("https://jsearch.p.rapidapi.com/search-v2")
        route.side_effect = [
            Response(200, json={"status": "OK", "data": {"jobs": batch1, "cursor": "c1"}}),
            Response(200, json={"status": "OK", "data": {"jobs": batch2, "cursor": "c2"}}),
        ]

        results = await adapter.fetch_raw()
        assert len(results) == 12
        assert len(respx_mock.calls) == 2

    # ── Cross-source normalisation check ─────────────────────────────────────

    def test_remoteok_and_jsearch_share_same_top_level_keys(self):
        """Both adapters must produce docs with the same top-level schema keys."""
        rok_adapter = RemoteOKAdapter()
        js_adapter = JSearchAdapter()

        rok_raw = [item for item in REMOTEOK_FIXTURE if "id" in item]
        rok_doc = rok_adapter.parse(rok_raw)[0]
        js_doc = js_adapter.parse(JSEARCH_FIXTURE["data"])[0]

        # Exclude non-schema housekeeping keys.
        exclude = {"raw", "ingested_at"}
        rok_keys = set(rok_doc.keys()) - exclude
        js_keys = set(js_doc.keys()) - exclude

        assert rok_keys == js_keys, (
            f"Schema mismatch between adapters.\n"
            f"RemoteOK only: {rok_keys - js_keys}\n"
            f"JSearch only: {js_keys - rok_keys}"
        )
