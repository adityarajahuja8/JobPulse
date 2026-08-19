"""MongoDB async client, collection accessors, and write helpers.

Collections
-----------
job_listings   — normalised job docs; unique index on (source, external_id)
run_logs       — per-run ingestion metrics
dead_letters   — raw anomalous/blocked responses saved for debugging
schema_snapshots — last known-good field set per source (for drift detection)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import motor.motor_asyncio
import pymongo
import structlog

from acdyon.config import settings

log = structlog.get_logger(__name__)

# ── Client ────────────────────────────────────────────────────────────────────

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None


def _get_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_url)
    return _client


def get_db() -> motor.motor_asyncio.AsyncIOMotorDatabase:
    """Return the Motor database instance.

    The database name is read from settings (defaults to 'acdyon').
    Tests can monkey-patch this function to inject a mock database.
    """
    return _get_client()[settings.mongodb_db_name]


# ── Index initialisation ──────────────────────────────────────────────────────


async def init_db() -> None:
    """Create all required indexes. Safe to call multiple times (idempotent)."""
    db = get_db()

    # Unique compound index — enforces dedup, powers idempotent upserts.
    await db.job_listings.create_index(
        [("source", pymongo.ASCENDING), ("external_id", pymongo.ASCENDING)],
        unique=True,
        name="source_external_id_unique",
    )

    # TTL or query indexes — useful for stats queries.
    await db.run_logs.create_index(
        [("started_at", pymongo.DESCENDING)],
        name="run_logs_started_at",
    )
    await db.dead_letters.create_index(
        [("source", pymongo.ASCENDING), ("recorded_at", pymongo.DESCENDING)],
        name="dead_letters_source_recorded_at",
    )
    await db.schema_snapshots.create_index(
        [("source", pymongo.ASCENDING)],
        unique=True,
        name="schema_snapshots_source_unique",
    )

    log.info("db.init_db.done", db=settings.mongodb_db_name)


# ── Write helpers ─────────────────────────────────────────────────────────────


async def upsert_listing(doc: dict[str, Any]) -> bool:
    """Upsert a normalised job listing.

    Returns True if a new document was inserted, False if an existing one was
    updated. The dedup key is (source, external_id).
    """
    db = get_db()
    result = await db.job_listings.update_one(
        filter={"source": doc["source"], "external_id": doc["external_id"]},
        update={"$set": {**doc, "ingested_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return result.upserted_id is not None


async def insert_run_log(log_doc: dict[str, Any]) -> None:
    """Append a run-log document to the run_logs collection."""
    db = get_db()
    await db.run_logs.insert_one(log_doc)


async def insert_dead_letter(item: dict[str, Any]) -> None:
    """Save a raw anomalous response to the dead_letters collection."""
    db = get_db()
    item.setdefault("recorded_at", datetime.now(timezone.utc))
    await db.dead_letters.insert_one(item)


# ── Schema snapshot helpers ───────────────────────────────────────────────────


async def get_schema_snapshot(source: str) -> set[str] | None:
    """Return the last known-good field set for a source, or None if not set."""
    db = get_db()
    doc = await db.schema_snapshots.find_one({"source": source})
    if doc is None:
        return None
    return set(doc.get("fields", []))


async def save_schema_snapshot(source: str, fields: set[str]) -> None:
    """Persist the current field set as the known-good schema for a source."""
    db = get_db()
    await db.schema_snapshots.update_one(
        {"source": source},
        {"$set": {"fields": sorted(fields), "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


# ── Query helpers ─────────────────────────────────────────────────────────────


async def get_recent_run_logs(n: int = 10) -> list[dict[str, Any]]:
    """Return the N most recent run-log documents."""
    db = get_db()
    cursor = db.run_logs.find().sort("started_at", pymongo.DESCENDING).limit(n)
    return await cursor.to_list(length=n)


async def get_dead_letters(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent dead-letter items."""
    db = get_db()
    cursor = db.dead_letters.find().sort("recorded_at", pymongo.DESCENDING).limit(limit)
    return await cursor.to_list(length=limit)


async def get_listing_count(source: str | None = None) -> int:
    """Return total listing count, optionally filtered by source."""
    db = get_db()
    query: dict[str, Any] = {}
    if source:
        query["source"] = source
    return await db.job_listings.count_documents(query)
