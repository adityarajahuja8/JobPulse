"""Ingestion runner — orchestrates a full ingestion cycle.

One cycle:
1. Iterate the enabled adapter chain (RemoteOK → Arbeitnow).
2. For each adapter:
   a. fetch_raw()  — with jittered pacing between requests
   b. validate()   — if anomaly: fallback ladder + dead-letter the raw response
   c. parse()      — normalise to unified schema
   d. schema-drift check against last known-good snapshot
   e. upsert_listing() for each normalised doc
   f. save updated schema snapshot
   g. write RunLog to MongoDB
3. Emit a structured summary log at cycle end.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from acdyon import db
from acdyon.config import settings
from acdyon.ingestion.base import SourceAdapter
from acdyon.ingestion.fallback import FallbackOrchestrator
from acdyon.ingestion.pacing import jittered_sleep
from acdyon.ingestion.validator import detect_schema_drift
from acdyon.sources.jsearch import JSearchAdapter
from acdyon.sources.remoteok import RemoteOKAdapter

log = structlog.get_logger(__name__)


def _build_adapter_chain() -> list[SourceAdapter]:
    """Return enabled adapters in priority order: RemoteOK first, JSearch second."""
    chain: list[SourceAdapter] = []
    if settings.remoteok_enabled:
        chain.append(RemoteOKAdapter())
    if settings.jsearch_enabled:
        chain.append(JSearchAdapter())
    return chain


async def _run_adapter(
    adapter: SourceAdapter,
    *,
    fallback: FallbackOrchestrator,
) -> dict[str, Any]:
    """Run one adapter and return a run-log dict.

    Handles validation failures, dead-lettering, schema drift, and upserts.
    """
    run_log: dict[str, Any] = {
        "source": adapter.source_id,
        "started_at": datetime.now(timezone.utc),
        "finished_at": None,
        "success_count": 0,
        "insert_count": 0,
        "update_count": 0,
        "block_count": 0,
        "schema_drift": False,
        "error": None,
    }

    log.info("runner.adapter.start", source=adapter.source_id)

    try:
        # ── 2a. Fetch ─────────────────────────────────────────────────────────
        raw = await adapter.fetch_raw()

        # ── 2b. Validate ──────────────────────────────────────────────────────
        validation = adapter.validate(raw)
        if not validation.ok:
            run_log["block_count"] += 1
            log.warning(
                "runner.validation_failed",
                source=adapter.source_id,
                reason=validation.reason,
            )
            # Dead-letter the raw response.
            await db.insert_dead_letter(
                {
                    "source": adapter.source_id,
                    "reason": validation.reason,
                    "raw_sample": raw[:3],  # Store a sample, not the full payload.
                }
            )
            # Run the fallback ladder.
            recovered = await fallback.handle_block(context={"reason": validation.reason})
            if not recovered:
                run_log["error"] = "fallback_exhausted"
                return run_log
            # If recovered, try once more with new identity.
            raw = await adapter.fetch_raw()
            validation = adapter.validate(raw)
            if not validation.ok:
                run_log["error"] = "validation_failed_after_fallback"
                return run_log

        # ── 2c. Parse ─────────────────────────────────────────────────────────
        docs = adapter.parse(raw)

        # ── 2d. Schema-drift check ────────────────────────────────────────────
        known_fields = await db.get_schema_snapshot(adapter.source_id)
        if known_fields:
            drift_result = detect_schema_drift(docs, known_fields, source_id=adapter.source_id)
            if not drift_result.ok:
                run_log["schema_drift"] = True
                await db.insert_dead_letter(
                    {
                        "source": adapter.source_id,
                        "reason": "schema_drift",
                        "details": drift_result.details,
                        "raw_sample": raw[:3],
                    }
                )
                log.error(
                    "runner.schema_drift_detected",
                    source=adapter.source_id,
                    details=drift_result.details,
                )
                run_log["error"] = "schema_drift"
                return run_log

        # ── 2e. Upsert ────────────────────────────────────────────────────────
        for doc in docs:
            inserted = await db.upsert_listing(doc)
            if inserted:
                run_log["insert_count"] += 1
            else:
                run_log["update_count"] += 1

        run_log["success_count"] = len(docs)

        # ── 2f. Save schema snapshot ──────────────────────────────────────────
        if docs:
            current_fields = set(docs[0].keys()) - {"raw", "ingested_at"}
            await db.save_schema_snapshot(adapter.source_id, current_fields)

    except Exception as exc:
        log.exception("runner.adapter.error", source=adapter.source_id, exc=str(exc))
        run_log["error"] = str(exc)

    finally:
        run_log["finished_at"] = datetime.now(timezone.utc)

    log.info(
        "runner.adapter.done",
        source=adapter.source_id,
        success=run_log["success_count"],
        inserted=run_log["insert_count"],
        updated=run_log["update_count"],
        blocks=run_log["block_count"],
        schema_drift=run_log["schema_drift"],
        error=run_log["error"],
    )
    return run_log


async def run_once() -> list[dict[str, Any]]:
    """Execute one full ingestion cycle across all enabled adapters.

    Returns a list of run-log dicts (one per adapter).
    """
    adapters = _build_adapter_chain()
    if not adapters:
        log.warning("runner.no_adapters_enabled")
        return []

    log.info("runner.cycle.start", adapters=[a.source_id for a in adapters])
    cycle_start = datetime.now(timezone.utc)
    run_logs: list[dict[str, Any]] = []

    for i, adapter in enumerate(adapters):
        fallback = FallbackOrchestrator(source_id=adapter.source_id)
        run_log = await _run_adapter(adapter, fallback=fallback)
        run_logs.append(run_log)
        await db.insert_run_log(run_log)

        # Jittered inter-adapter pacing (not strictly necessary for public APIs
        # that differ by domain, but keeps the runner consistent with the
        # log-normal pacing principle throughout).
        if i < len(adapters) - 1:
            await jittered_sleep(
                mu=settings.default_pacing_mu,
                sigma=settings.default_pacing_sigma,
                label="runner.inter_adapter",
            )

    cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
    total_listings = sum(r["success_count"] for r in run_logs)
    total_inserts = sum(r["insert_count"] for r in run_logs)
    total_updates = sum(r["update_count"] for r in run_logs)
    errors = [r["error"] for r in run_logs if r["error"]]

    log.info(
        "runner.cycle.done",
        duration_s=round(cycle_duration, 1),
        total_listings=total_listings,
        new_inserts=total_inserts,
        updates=total_updates,
        errors=errors or None,
    )
    return run_logs
