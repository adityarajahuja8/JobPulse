# Acdyon

Resilient, ethical job-listing ingestion pipeline.

Pulls job listings from **RemoteOK** (primary) and **Arbeitnow** (backup),
normalises them into a unified schema, and stores them in MongoDB. Built to
demonstrate the ingestion architecture described in `DESIGN.md` — pacing,
identity, fallback ladder, schema-drift detection, and dead-letter queuing.

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- MongoDB running locally (`mongod`) — or provide an Atlas connection string

### 2. Install

```bash
git clone <repo>
cd acdyon
cp .env.example .env          # edit if needed
pip install -e .[dev]
```

### 3. Initialise the database

```bash
acdyon init-db
```

Creates indexes on `job_listings(source, external_id)` and `run_logs`.

### 4. Run a one-shot ingestion

```bash
acdyon run
```

Fetches from RemoteOK, then Arbeitnow. Normalises and upserts into MongoDB.
Re-running is safe — documents are upserted on `(source, external_id)`, never
duplicated.

### 5. Check stats

```bash
acdyon stats
```

### 6. Continuous watch mode

```bash
acdyon watch            # runs every RUN_INTERVAL_SECONDS (default: 300)
```

---

## CLI Reference

| Command | Description |
|---|---|
| `acdyon init-db` | Create MongoDB indexes |
| `acdyon run` | One-shot ingestion from all enabled sources |
| `acdyon watch` | Scheduled continuous ingestion |
| `acdyon stats [--n N]` | Last N run logs |
| `acdyon deadletter` | List dead-letter (anomalous/blocked) items |
| `acdyon sources` | Show enabled adapters and last run status |

---

## Architecture

```
RemoteOK API ──┐
               ├── SourceAdapter (base.py)
Arbeitnow API ─┘        │
                         ▼
               pacing.py (log-normal jitter)
               validator.py (anomaly detection)
               fallback.py (back-off ladder)
                         │
                         ▼
               runner.py (orchestrates cycle)
                         │
                         ▼
               db.py → MongoDB
               ├── job_listings  (upserted, deduplicated)
               ├── run_logs      (per-run metrics)
               └── dead_letters  (anomalous responses)
```

See `DESIGN.md` for the full ingestion architecture.
See `DECISIONS.md` for ToS commitments and out-of-scope boundaries.

---

## Running Tests

```bash
pytest tests/ -v
```

No real MongoDB or network calls required — all mocked via `mongomock-motor`
and `respx`.

---

## Environment Variables

See `.env.example` for all options. Key ones:

| Variable | Default | Description |
|---|---|---|
| `MONGODB_URL` | `mongodb://localhost:27017/acdyon` | MongoDB connection string |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `RUN_INTERVAL_SECONDS` | `300` | Watch mode interval |
| `PROXY_URL` | *(blank)* | Optional proxy — not needed for demo |
| `REMOTEOK_ENABLED` | `true` | Enable RemoteOK adapter |
| `ARBEITNOW_ENABLED` | `true` | Enable Arbeitnow adapter |
