"""Tests for FastAPI server endpoints and MongoDB listing collection accessors."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from acdyon import db as db_module
from acdyon.server import app


class TestServerEndpoints:

    def test_listings_coll_constant_exists(self):
        """Verify LISTINGS_COLL constant is exported from acdyon.db."""
        assert hasattr(db_module, "LISTINGS_COLL")
        assert db_module.LISTINGS_COLL == "job_listings"

    @pytest.mark.asyncio
    async def test_get_listings_returns_mongodb_data(self, mock_db):
        """GET /api/listings should retrieve stored MongoDB listings directly."""
        # Seed mock_db with sample normalized documents
        sample_docs = [
            {
                "source": "remoteok",
                "external_id": "rok-101",
                "title": "Backend Python Developer",
                "company": "Remote Corp",
                "location": "Worldwide",
                "url": "https://remoteok.com/remote-jobs/rok-101",
                "remote": True,
                "posted_at": "2026-08-19T10:00:00Z",
                "ingested_at": "2026-08-19T10:05:00Z",
            },
            {
                "source": "jsearch",
                "external_id": "js-202",
                "title": "Staff Fullstack Engineer",
                "company": "Rapid Tech",
                "location": "San Francisco, CA",
                "url": "https://jsearch.p.rapidapi.com/job/js-202",
                "remote": True,
                "posted_at": "2026-08-19T09:00:00Z",
                "ingested_at": "2026-08-19T09:05:00Z",
            },
        ]

        await mock_db[db_module.LISTINGS_COLL].insert_many(sample_docs)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get("/api/listings")
            assert res.status_code == 200
            payload = res.json()
            assert payload["status"] == "ok"
            assert payload["total"] == 2
            data = payload["data"]

            sources = {d["source"] for d in data}
            assert "remoteok" in sources
            assert "jsearch" in sources

    @pytest.mark.asyncio
    async def test_get_listings_filter_by_source(self, mock_db):
        """GET /api/listings?source=jsearch should return only jsearch jobs."""
        await mock_db[db_module.LISTINGS_COLL].insert_many([
            {"source": "remoteok", "external_id": "rok-1", "title": "Dev 1", "company": "A", "url": "http://a.com"},
            {"source": "jsearch", "external_id": "js-1", "title": "Dev 2", "company": "B", "url": "http://b.com"},
        ])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get("/api/listings?source=jsearch")
            assert res.status_code == 200
            payload = res.json()
            assert payload["total"] == 1
            assert payload["data"][0]["source"] == "jsearch"

    @pytest.mark.asyncio
    async def test_post_ingest_endpoint(self, mock_db, monkeypatch):
        """POST /api/ingest should trigger run_once()."""
        run_called = False

        async def mock_run_once(*args, **kwargs):
            nonlocal run_called
            run_called = True
            return [{"source": "test", "success_count": 5}]

        monkeypatch.setattr("acdyon.server.run_once", mock_run_once)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post("/api/ingest")
            assert res.status_code == 200
            assert run_called is True
            assert res.json()["status"] == "ok"
