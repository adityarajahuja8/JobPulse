"""Unit tests for source adapters.

Network is fully mocked via respx — no real HTTP calls.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import respx
from httpx import Response

from tests.conftest import JSEARCH_FIXTURE, REMOTEOK_FIXTURE
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
