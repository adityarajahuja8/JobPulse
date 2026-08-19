"""Shared pytest fixtures.

Uses mongomock-motor so tests never need a real MongoDB instance.
Uses respx to mock httpx calls so tests never make real network requests.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

import acdyon.db as db_module
from acdyon.config import settings


# ── MongoDB mock ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def mock_db(monkeypatch):
    """Replace the Motor client with an in-memory mongomock client and zero out delays."""
    mock_client = AsyncMongoMockClient()
    mock_database = mock_client[settings.mongodb_db_name]

    monkeypatch.setattr(db_module, "get_db", lambda: mock_database)
    monkeypatch.setattr(settings, "global_throttle_seconds", 0.001)
    monkeypatch.setattr(settings, "default_pacing_mu", 0.001)

    # Initialise indexes (mongomock supports index creation).
    await db_module.init_db()

    yield mock_database


# ── Fixture JSON for RemoteOK ─────────────────────────────────────────────────

REMOTEOK_FIXTURE: list[dict] = [
    # First element is always metadata — should be skipped by the adapter.
    {"legal": "This data is property of Remote OK"},
    {
        "id": "12345",
        "epoch": 1700000000,
        "date": "2023-11-14T22:13:20+00:00",
        "position": "Senior Python Engineer",
        "company": "Acme Corp",
        "location": "Worldwide",
        "url": "https://remoteok.com/remote-jobs/12345",
        "tags": ["python", "backend", "senior"],
        "salary_min": "100000",
        "salary_max": "140000",
    },
    {
        "id": "12346",
        "epoch": 1700001000,
        "position": "React Developer",
        "company": "Beta Inc",
        "location": "USA Only",
        "url": "https://remoteok.com/remote-jobs/12346",
        "tags": ["react", "frontend"],
        "salary_min": None,
        "salary_max": None,
    },
]

# ── Fixture JSON for JSearch (RapidAPI) ───────────────────────────────────────

JSEARCH_FIXTURE: dict = {
    "status": "OK",
    "request_id": "test-req-12345",
    "parameters": {"query": "Python developer", "page": 1, "num_pages": 1},
    "data": [
        {
            "job_id": "google-swe-12345",
            "employer_name": "Google",
            "job_title": "Senior Cloud Infrastructure Engineer",
            "job_apply_link": "https://careers.google.com/jobs/results/12345",
            "job_city": "Mountain View",
            "job_state": "CA",
            "job_country": "US",
            "job_is_remote": True,
            "job_posted_at_timestamp": 1700000000,
            "job_posted_at_datetime_utc": "2023-11-14T22:13:20.000Z",
            "job_min_salary": 180000,
            "job_max_salary": 250000,
            "job_employment_type": "FULLTIME",
            "job_required_skills": ["python", "kubernetes", "gcp"],
        },
        {
            "job_id": "microsoft-fe-67890",
            "employer_name": "Microsoft",
            "job_title": "Staff Frontend Engineer",
            "job_apply_link": "https://careers.microsoft.com/us/en/job/67890",
            "job_city": "Redmond",
            "job_state": "WA",
            "job_country": "US",
            "job_is_remote": False,
            "job_posted_at_timestamp": 1700001000,
            "job_posted_at_datetime_utc": "2023-11-14T22:30:00.000Z",
            "job_min_salary": None,
            "job_max_salary": None,
            "job_employment_type": "FULLTIME",
            "job_required_skills": ["react", "typescript"],
        },
    ],
}
