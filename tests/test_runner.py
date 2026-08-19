"""Integration tests for the ingestion runner.

Uses mock adapters and mongomock-motor — no real network or DB calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from acdyon import db as db_module
from acdyon.ingestion.base import SourceAdapter, ValidationResult
from acdyon.runner import run_once
from tests.conftest import JSEARCH_FIXTURE, REMOTEOK_FIXTURE


# ── Stub adapters ─────────────────────────────────────────────────────────────


class _StubRemoteOKAdapter(SourceAdapter):
    """In-memory stub that returns RemoteOK fixture data synchronously."""

    source_id = "remoteok"
    display_name = "RemoteOK (stub)"

    async def fetch_raw(self) -> list[dict[str, Any]]:
        return [item for item in REMOTEOK_FIXTURE if "id" in item]

    def validate(self, raw):
        return ValidationResult(ok=True)

    def parse(self, raw):
        from acdyon.sources.remoteok import RemoteOKAdapter
        return RemoteOKAdapter().parse(raw)


class _StubJSearchAdapter(SourceAdapter):
    """In-memory stub that returns JSearch fixture data."""

    source_id = "jsearch"
    display_name = "JSearch (stub)"

    async def fetch_raw(self) -> list[dict[str, Any]]:
        return JSEARCH_FIXTURE["data"]

    def validate(self, raw):
        return ValidationResult(ok=True)

    def parse(self, raw):
        from acdyon.sources.jsearch import JSearchAdapter
        return JSearchAdapter().parse(raw)


class _AlwaysBlocksAdapter(SourceAdapter):
    """Adapter whose validation always fails (simulates a blocked source)."""

    source_id = "blocked_source"
    display_name = "Always Blocked"

    async def fetch_raw(self):
        return [{"id": "x"}]

    def validate(self, raw):
        return ValidationResult(ok=False, reason="captcha_detected")

    def parse(self, raw):
        return []


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestRunnerIntegration:

    @pytest.mark.asyncio
    async def test_run_inserts_listings_from_both_sources(self, mock_db, monkeypatch):
        """Runner should upsert listings from both stub adapters."""
        monkeypatch.setattr(
            "acdyon.runner._build_adapter_chain",
            lambda: [_StubRemoteOKAdapter(), _StubJSearchAdapter()],
        )
        monkeypatch.setattr(db_module, "get_db", lambda: mock_db)

        run_logs = await run_once()

        assert len(run_logs) == 2

        remoteok_log = next(r for r in run_logs if r["source"] == "remoteok")
        jsearch_log = next(r for r in run_logs if r["source"] == "jsearch")

        assert remoteok_log["success_count"] == 2
        assert jsearch_log["success_count"] == 2
        assert remoteok_log["error"] is None
        assert jsearch_log["error"] is None

    @pytest.mark.asyncio
    async def test_idempotent_upsert_no_duplicates(self, mock_db, monkeypatch):
        """Running twice should not duplicate documents in MongoDB."""
        monkeypatch.setattr(
            "acdyon.runner._build_adapter_chain",
            lambda: [_StubRemoteOKAdapter()],
        )
        monkeypatch.setattr(db_module, "get_db", lambda: mock_db)

        # First run.
        logs1 = await run_once()
        count_after_first = await db_module.get_listing_count("remoteok")

        # Second run with identical data.
        logs2 = await run_once()
        count_after_second = await db_module.get_listing_count("remoteok")

        assert count_after_first == count_after_second, (
            f"Duplicate documents found: {count_after_first} → {count_after_second}"
        )
        # Second run should report updates, not inserts.
        assert logs2[0]["insert_count"] == 0
        assert logs2[0]["update_count"] == 2

    @pytest.mark.asyncio
    async def test_run_log_written_to_db(self, mock_db, monkeypatch):
        """A RunLog document should be written to MongoDB after each adapter run."""
        monkeypatch.setattr(
            "acdyon.runner._build_adapter_chain",
            lambda: [_StubRemoteOKAdapter()],
        )
        monkeypatch.setattr(db_module, "get_db", lambda: mock_db)

        await run_once()

        logs = await db_module.get_recent_run_logs(10)
        assert len(logs) >= 1
        log_doc = logs[0]
        assert log_doc["source"] == "remoteok"
        assert log_doc["success_count"] == 2

    @pytest.mark.asyncio
    async def test_blocked_adapter_dead_letters_and_continues(self, mock_db, monkeypatch):
        """A blocked adapter should dead-letter the response and not crash the runner."""
        monkeypatch.setattr(
            "acdyon.runner._build_adapter_chain",
            lambda: [_AlwaysBlocksAdapter()],
        )
        monkeypatch.setattr(db_module, "get_db", lambda: mock_db)

        run_logs = await run_once()

        # Runner should complete (not raise).
        assert len(run_logs) == 1
        log = run_logs[0]
        assert log["block_count"] >= 1

        # Dead-letter should have an entry.
        dl_items = await db_module.get_dead_letters()
        assert len(dl_items) >= 1
        assert dl_items[0]["source"] == "blocked_source"

    @pytest.mark.asyncio
    async def test_no_adapters_enabled_returns_empty_logs(self, mock_db, monkeypatch):
        """If no adapters are enabled, runner returns empty list gracefully."""
        monkeypatch.setattr(
            "acdyon.runner._build_adapter_chain",
            lambda: [],
        )
        monkeypatch.setattr(db_module, "get_db", lambda: mock_db)

        run_logs = await run_once()
        assert run_logs == []
