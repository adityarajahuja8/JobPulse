"""FastAPI server for Acdyon.

Serves live ingested job listings, run logs, and metrics directly to the web client.
"""

from __future__ import annotations

from typing import Any
import structlog
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from acdyon import db
from acdyon.runner import run_once

log = structlog.get_logger(__name__)

app = FastAPI(
    title="Acdyon Ingestion API",
    description="Live REST API for Acdyon Job Listings Ingestion Pipeline",
    version="0.1.0",
)

# Enable CORS for Vite dev server (port 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "JobPulse / Acdyon Ingestion API",
        "endpoints": {
            "health": "/api/health",
            "listings": "/api/listings",
            "stats": "/api/stats",
            "run": "/api/run"
        }
    }


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "acdyon-engine"}


@app.get("/api/listings")
async def get_listings(
    source: str | None = Query(default=None, description="Filter by source (remoteok | jsearch)"),
    limit: int = Query(default=50, ge=1, le=200, description="Max listings to return"),
    force_refresh: bool = Query(default=False, description="Run live ingestion before returning"),
) -> dict[str, Any]:
    """Retrieve normalized job listings from MongoDB, or trigger a live fetch."""
    if force_refresh:
        log.info("api.get_listings.force_refresh")
        await run_once()

    listings: list[dict[str, Any]] = []

    try:
        database = db.get_db()
        query: dict[str, Any] = {}
        if source:
            query["source"] = source

        cursor = (
            database[db.LISTINGS_COLL]
            .find(query, {"_id": 0, "raw": 0})
            .sort("posted_at", -1)
            .limit(limit)
        )
        listings = await cursor.to_list(length=limit)

        # If DB is empty, run a one-shot ingestion automatically
        if not listings:
            log.info("api.get_listings.empty_db_triggering_run")
            await run_once()
            cursor = (
                database[db.LISTINGS_COLL]
                .find(query, {"_id": 0, "raw": 0})
                .sort("posted_at", -1)
                .limit(limit)
            )
            listings = await cursor.to_list(length=limit)

    except Exception as db_err:
        log.warning("api.get_listings.db_fallback_to_live", error=str(db_err))
        # Live fetch fallback directly from enabled adapters
        if source == "remoteok" or not source:
            from acdyon.sources.remoteok import RemoteOKAdapter
            rok_adapter = RemoteOKAdapter()
            rok_raw = await rok_adapter.fetch_raw()
            rok_docs = rok_adapter.parse(rok_raw)
            for d in rok_docs:
                d.pop("raw", None)
            listings.extend(rok_docs)

        if source == "jsearch" or not source:
            from acdyon.sources.jsearch import JSearchAdapter
            js_adapter = JSearchAdapter()
            js_raw = await js_adapter.fetch_raw()
            js_docs = js_adapter.parse(js_raw)
            for d in js_docs:
                d.pop("raw", None)
            listings.extend(js_docs)

        if limit and len(listings) > limit:
            listings = listings[:limit]

    return {
        "status": "ok",
        "total": len(listings),
        "data": listings,
    }


@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    """Return pipeline telemetry and run logs."""
    logs = await db.get_recent_run_logs(10)
    # Clean _id
    for l in logs:
        l.pop("_id", None)
    return {"status": "ok", "logs": logs}


@app.post("/api/run")
async def trigger_run() -> dict[str, Any]:
    """Trigger a live ingestion cycle immediately."""
    run_logs = await run_once()
    return {"status": "ok", "run_logs": run_logs}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("acdyon.server:app", host="0.0.0.0", port=8000, reload=True)
