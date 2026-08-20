# JobPulse (Acdyon Ingestion Engine)

[![Tests](https://img.shields.io/badge/tests-66%20passed-brightgreen.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Vite](https://img.shields.io/badge/vite-5.4+-646CFF.svg)](https://vitejs.dev)

A resilient, ethical, and 100% server-driven job-listing ingestion engine and live web client.

Pulls job listings from **RemoteOK** and **JSearch RapidAPI** (`/search-v2`), normalizes them into a unified canonical schema, stores them in MongoDB with compound unique index deduplication, and serves them via a Python FastAPI REST API.

---

## Architecture Overview

```
Vercel Frontend (https://job-pulse-green.vercel.app)
      │
      │ HTTPS (VITE_API_BASE_URL)
      ▼
Deployed Python FastAPI Backend (/api/listings & /api/ingest)
      │
      ├──── MongoDB (job_listings collection)
      │
      ├──── RemoteOK API
      │
      └──── JSearch RapidAPI (/search-v2)
```

- **Single Source of Truth**: The Python backend manages all ingestion and database queries. The browser does **not** directly query external APIs or run client-side ingestion logic.
- **Resilient Pipeline**: Log-normal pacing jitter, 5-step exponential fallback ladder, schema-drift detection, and dead-letter queuing.
- **Zero API Secrets Leakage**: `RAPIDAPI_KEY` and `MONGODB_URL` remain strictly secured on the backend. Frontend only references `VITE_API_BASE_URL`.

---

## Live Demo & Endpoints

- **GitHub Repository**: [github.com/adityarajahuja8/JobPulse](https://github.com/adityarajahuja8/JobPulse)
- **Deployed Frontend**: [job-pulse-green.vercel.app](https://job-pulse-green.vercel.app/)
- **Backend Endpoints**:
  - `GET /api/listings` — Returns normalized job listings directly from MongoDB (`limit=200`, sorted by `posted_at DESC`). Filterable by `source` (`remoteok` | `jsearch`).
  - `POST /api/ingest` — Triggers an on-demand live pipeline ingestion cycle.
  - `GET /api/stats` — Pipeline telemetry and run logs.
  - `GET /api/health` — API health check.

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

Creates unique compound index `(source, external_id)` on `job_listings` ensuring 100% idempotent upserts.

### 4. Run Pipeline Ingestion

```bash
python -m acdyon.cli run
```

Fetches from RemoteOK and JSearch, normalizes documents, checks schema drift, and upserts into MongoDB.

### 5. Start Backend Server & Web Frontend

**Backend (FastAPI on port 8000)**:
```bash
python -m uvicorn acdyon.server:app --port 8000 --reload
```

**Frontend (Vite on port 3000)**:
```bash
cd web
npm install
npm run dev
```

Open **`http://localhost:3000`** in your browser. Local API requests (`/api/*`) are automatically proxied to `http://localhost:8000`.

---

## Environment Variables

### Backend (`.env`)
```env
MONGODB_URL=mongodb://localhost:27017/acdyon
RAPIDAPI_KEY=your_rapidapi_key_here
RAPIDAPI_HOST=jsearch.p.rapidapi.com
REMOTEOK_ENABLED=true
JSEARCH_ENABLED=true
```

### Frontend (`web/.env` or Vercel Environment Variables)
```env
VITE_API_BASE_URL=https://your-backend-api.com
```

---

## CLI Reference

| Command | Description |
|---|---|
| `python -m acdyon.cli init-db` | Create MongoDB indexes on `job_listings`, `run_logs`, etc. |
| `python -m acdyon.cli run` | Execute one-shot ingestion from all enabled sources |
| `python -m acdyon.cli watch` | Scheduled continuous background ingestion |
| `python -m acdyon.cli stats` | View last N run performance logs |
| `python -m acdyon.cli sources` | Inspect enabled adapters, roles, and DB record counts |
| `python -m acdyon.cli deadletter` | Inspect anomalous / quarantined payloads |

---

## Running Automated Tests

```bash
python -m pytest
```

**66 unit & integration tests** cover:
- **Server & Database**: `GET /api/listings` MongoDB queries, collection constants (`db.LISTINGS_COLL`), source filtering (`remoteok` / `jsearch`), CORS headers, and `POST /api/ingest`.
- **Adapters**: RemoteOK & JSearch parsing, direct link verification, date handling.
- **Pacing**: Log-normal distribution and delay bounds.
- **Validator**: Schema drift & block-page detection.
- **Fallback**: Circuit-breaker and 5-step de-escalation ladder.
