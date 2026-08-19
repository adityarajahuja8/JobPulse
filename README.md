# JobPulse (Acdyon Pipeline)

[![Tests](https://img.shields.io/badge/tests-45%20passed-brightgreen.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Vite](https://img.shields.io/badge/vite-5.4+-646CFF.svg)](https://vitejs.dev)

A resilient, ethical, and fully observable job-listing ingestion pipeline and live dashboard.

Pulls job listings from **RemoteOK** (primary) and **JSearch RapidAPI** (backup / enterprise tech stream), normalises them into a unified schema, and stores them in MongoDB with compound unique index deduplication. Features log-normal pacing jitter, 5-step exponential fallback ladder, schema-drift detection, and dead-letter queuing.

---

## Live Demo & Architecture

- **GitHub Repository**: [github.com/adityarajahuja8/JobPulse](https://github.com/adityarajahuja8/JobPulse)
- **Frontend Dashboard**: Vite + HTML/CSS/JS with live streaming, search/filter chips, and 8-item pagination.
- **Backend API**: FastAPI REST endpoints on port 8000 (`GET /api/listings`, `GET /api/stats`, `POST /api/run`).
- **CLI Engine**: Typer-powered pipeline manager (`init-db`, `run`, `watch`, `stats`, `sources`, `deadletter`).

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- MongoDB (`mongod` locally on `mongodb://localhost:27017` or MongoDB Atlas URI)
- Node.js 18+ (for frontend web client)

### 2. Installation & Setup

```bash
git clone https://github.com/adityarajahuja8/JobPulse.git
cd JobPulse

# Python virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .[dev]

# Copy environment config
cp .env.example .env
```

### 3. Initialize Database Indexes

```bash
python -m acdyon.cli init-db
```

Creates unique compound index `(source, external_id)` ensuring 100% idempotent upserts.

### 4. Run One-Shot Ingestion

```bash
python -m acdyon.cli run
```

Fetches from RemoteOK and JSearch, normalizes, detects anomalies/drift, and upserts into MongoDB.

```
                          Run Results                           
┌──────────┬──────────┬─────┬─────────┬────────┬───────┬───────┐
│ Source   │ Listings │ New │ Updated │ Blocks │ Drift │ Error │
├──────────┼──────────┼─────┼─────────┼────────┼───────┼───────┤
│ remoteok │      100 │   0 │     100 │      0 │   ✓   │ None  │
│ jsearch  │        8 │   0 │       8 │      0 │   ✓   │ None  │
└──────────┴──────────┴─────┴─────────┴────────┴───────┴───────┘
```

### 5. Launch the Web Frontend Dashboard

```bash
cd web
npm install
npm run dev
```

Open **`http://localhost:3000`** in your browser.

---

## CLI Reference

| Command | Description |
|---|---|
| `python -m acdyon.cli init-db` | Create MongoDB indexes |
| `python -m acdyon.cli run` | Execute one-shot ingestion from all enabled sources |
| `python -m acdyon.cli watch` | Scheduled continuous background ingestion |
| `python -m acdyon.cli stats` | View last N run performance logs |
| `python -m acdyon.cli sources` | Inspect enabled adapters, roles, and DB record counts |
| `python -m acdyon.cli deadletter` | Inspect anomalous / quarantined payloads |

---

## Pipeline Architecture

```
RemoteOK API ──────┐
                   ├── SourceAdapter (base.py)
JSearch RapidAPI ──┘        │
                            ▼
                   pacing.py (log-normal distribution)
                   validator.py (schema drift & block detection)
                   fallback.py (5-step back-off ladder)
                            │
                            ▼
                   runner.py (orchestrates ingestion cycle)
                            │
                            ▼
                   db.py → MongoDB
                   ├── job_listings    (compound unique index)
                   ├── run_logs        (cycle metrics & timings)
                   ├── schema_snapshots (drift detection baseline)
                   └── dead_letters    (quarantined anomalies)
```

---

## Running Automated Tests

```bash
python -m pytest tests/ -v
```

**45 unit & integration tests** cover:
- Adapters (RemoteOK & JSearch parsing, direct link verification, date handling)
- Pacing engine (Log-normal distribution, μ/σ drift bounds)
- Fallback ladder (Circuit-breaker, exponential back-off)
- Schema drift & block-page detection (HTML challenge / Captcha traps)
- Database upsert idempotency & compound uniqueness
