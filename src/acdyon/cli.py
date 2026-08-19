"""Acdyon CLI — Typer-based command line interface.

Commands:
    acdyon init-db      Create MongoDB indexes
    acdyon run          One-shot ingestion
    acdyon watch        Continuous scheduled ingestion
    acdyon stats        Last N run logs
    acdyon deadletter   List dead-letter items
    acdyon sources      Show enabled adapters
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import timezone
from typing import Annotated

# Ensure safe UTF-8 output on Windows terminals
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import structlog
import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from acdyon import db
from acdyon.config import settings
from acdyon.runner import run_once

# ── Logging setup ─────────────────────────────────────────────────────────────
import logging

import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    ),
)

app = typer.Typer(
    name="acdyon",
    help="Resilient job-listing ingestion pipeline.",
    pretty_exceptions_enable=False,
)
console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_async(coro):
    """Run an async coroutine from a sync Typer command."""
    return asyncio.run(coro)


def _fmt_dt(dt) -> str:
    if dt is None:
        return "—"
    if hasattr(dt, "astimezone"):
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(dt)


# ── Commands ──────────────────────────────────────────────────────────────────


@app.command("init-db")
def init_db_cmd():
    """Create MongoDB indexes. Safe to run multiple times."""
    rprint("[bold cyan]Initialising MongoDB indexes…[/]")
    _run_async(db.init_db())
    rprint("[bold green]✓ Done.[/]")


@app.command("run")
def run_cmd(
    total_jobs: Annotated[
        int | None,
        typer.Option(
            "--total-jobs",
            "-n",
            help="Total number of jobs to fetch from JSearch (e.g. 10, 20, 50, 100).",
        ),
    ] = None,
):
    """Execute a one-shot ingestion cycle across all enabled sources."""
    rprint("[bold cyan]Starting ingestion run…[/]")
    run_logs = _run_async(run_once(jsearch_total_jobs=total_jobs))

    table = Table(title="Run Results", show_header=True, header_style="bold magenta")
    table.add_column("Source")
    table.add_column("Listings", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Updated", justify="right")
    table.add_column("Blocks", justify="right")
    table.add_column("Drift", justify="center")
    table.add_column("Error")

    for r in run_logs:
        drift_str = "⚠" if r.get("schema_drift") else "✓"
        table.add_row(
            r.get("source", ""),
            str(r.get("success_count", 0)),
            str(r.get("insert_count", 0)),
            str(r.get("update_count", 0)),
            str(r.get("block_count", 0)),
            drift_str,
            str(r.get("error") or ""),
        )

    console.print(table)


@app.command("watch")
def watch_cmd():
    """Run ingestion on a recurring schedule (RUN_INTERVAL_SECONDS)."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    interval = settings.run_interval_seconds
    rprint(f"[bold cyan]Watch mode — running every {interval}s. Press Ctrl+C to stop.[/]")

    scheduler = BlockingScheduler()
    scheduler.add_job(
        lambda: asyncio.run(run_once()),
        "interval",
        seconds=interval,
        id="ingestion",
    )
    # Run immediately on start.
    asyncio.run(run_once())
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        rprint("[yellow]Watch mode stopped.[/]")


@app.command("stats")
def stats_cmd(
    n: Annotated[int, typer.Option("--n", help="Number of recent runs to show")] = 10,
):
    """Display the last N ingestion run logs."""
    logs = _run_async(db.get_recent_run_logs(n))

    if not logs:
        rprint("[yellow]No run logs found. Run [bold]acdyon run[/] first.[/]")
        return

    table = Table(title=f"Last {n} Run Logs", show_header=True, header_style="bold magenta")
    table.add_column("Source")
    table.add_column("Started (UTC)")
    table.add_column("Listings", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Updated", justify="right")
    table.add_column("Blocks", justify="right")
    table.add_column("Drift", justify="center")
    table.add_column("Error")

    for r in logs:
        drift_str = "[red]⚠[/]" if r.get("schema_drift") else "[green]✓[/]"
        table.add_row(
            r.get("source", ""),
            _fmt_dt(r.get("started_at")),
            str(r.get("success_count", 0)),
            str(r.get("insert_count", 0)),
            str(r.get("update_count", 0)),
            str(r.get("block_count", 0)),
            drift_str,
            str(r.get("error") or ""),
        )

    console.print(table)


@app.command("deadletter")
def deadletter_cmd(
    limit: Annotated[int, typer.Option("--limit", help="Max items to show")] = 20,
):
    """List dead-letter (anomalous/blocked) items."""
    items = _run_async(db.get_dead_letters(limit))

    if not items:
        rprint("[green]Dead-letter queue is empty. 🎉[/]")
        return

    table = Table(title="Dead Letters", show_header=True, header_style="bold red")
    table.add_column("Source")
    table.add_column("Recorded (UTC)")
    table.add_column("Reason")
    table.add_column("Details")

    for item in items:
        table.add_row(
            item.get("source", ""),
            _fmt_dt(item.get("recorded_at")),
            str(item.get("reason") or ""),
            json.dumps(item.get("details") or {})[:80],
        )

    console.print(table)


@app.command("sources")
def sources_cmd():
    """Show configured source adapters and their enabled state."""
    from acdyon.sources.jsearch import JSearchAdapter
    from acdyon.sources.remoteok import RemoteOKAdapter

    adapters = [
        (RemoteOKAdapter.source_id, RemoteOKAdapter.display_name, settings.remoteok_enabled, "Primary"),
        (JSearchAdapter.source_id, JSearchAdapter.display_name, settings.jsearch_enabled, "Backup"),
    ]

    table = Table(title="Source Adapters", show_header=True, header_style="bold magenta")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Enabled", justify="center")
    table.add_column("Role")
    table.add_column("DB Count", justify="right")

    async def _get_counts():
        counts = {}
        for sid, *_ in adapters:
            counts[sid] = await db.get_listing_count(sid)
        return counts

    counts = _run_async(_get_counts())

    for sid, name, enabled, role in adapters:
        enabled_str = "[green]YES[/]" if enabled else "[red]NO[/]"
        table.add_row(sid, name, enabled_str, role, str(counts.get(sid, 0)))

    console.print(table)


if __name__ == "__main__":
    app()
