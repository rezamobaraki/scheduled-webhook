# Timer Service

A horizontally-scalable webhook scheduling service built with
**FastAPI · Celery · PostgreSQL · Redis**.

---

## Architecture

```text
                LAYER 1 — DURABILITY               LAYER 2 — PRECISION
            ┌────────────────────────┐          ┌─────────────────────────┐
            │      PostgreSQL        │          │     Redis  +  Celery    │
POST /timer─▶  (source of truth)    │──dispatch─▶  (timely delivery)     │
            │                        │          │                         │
            └───────────┬────────────┘          └────────────┬────────────┘
                        │                                    │
                        │ sweep (every 30 s)                 │ fire at ETA
                        │ ◀─── Celery Beat ──────────────────┘
                        │     (recovery safety-net)          │
                        │                                    ▼
                        │                              POST webhook
                        │                                    │
                        └────────────────────────────────────┘
                          UPDATE status = 'executed'
```

| Concern | How it is solved |
|---|---|
| **Persistence** | PostgreSQL stores every timer before dispatching to broker |
| **Precision** | Celery `apply_async(eta=…)` fires at the right instant |
| **Restart recovery** | Beat sweeps every 30 s for overdue pending timers |
| **Exactly-once** | `SELECT … FOR UPDATE` + `WHERE status='pending'` |
| **Horizontal scale** | Stateless API replicas · competing Celery workers |
| **Retry** | Exponential back-off (5 s → 10 s → 20 s), then `FAILED` |

### Project structure

```
src/
├── main.py                    FastAPI app + lifespan
├── core/
│   ├── config.py              Pydantic Settings (composed, not hardcoded)
│   └── database.py            Async + Sync SQLAlchemy engines
├── models/
│   ├── base.py                DeclarativeBase
│   ├── enums.py               TimerStatus enum
│   └── timer.py               Timer ORM model
├── schemas/
│   ├── timer_create_request.py  Pydantic request DTO
│   ├── timer_create_response.py Pydantic response DTO (create)
│   └── timer_get_response.py    Pydantic response DTO (get)
├── repository/
│   └── timer.py               TimerRepository (async) + SyncTimerRepository
├── services/
│   └── timer.py               TimerService — business logic
├── routers/
│   └── timers.py              POST /timer · GET /timer/{id}
└── worker/
    ├── celery_app.py           Celery configuration
    └── tasks.py                fire_webhook · sweep_overdue_timers
```

### Layer dependency flow

```
Router  →  Service  →  Repository  →  SQLAlchemy Session  →  PostgreSQL
              ↓
         Celery Task dispatch
```

---

## Quick Start

```bash
# 1. Copy environment template
cp .env.example .env          # edit if needed

# 2. Build and start everything
docker compose up --build

# API:   http://localhost:8000
# Docs:  http://localhost:8000/docs
```

## Configuration

All settings come from environment variables (or a `.env` file).
Nothing is hardcoded — each domain has its own prefix:

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | — | PostgreSQL hostname |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_USER` | — | PostgreSQL username |
| `POSTGRES_PASSWORD` | — | PostgreSQL password |
| `POSTGRES_DB` | — | Database name |
| `REDIS_HOST` | — | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database index |
| `WEBHOOK_TIMEOUT` | `10` | HTTP timeout per webhook call (seconds) |
| `WEBHOOK_MAX_RETRIES` | `3` | Retry attempts before marking `failed` |
| `APP_SWEEP_INTERVAL` | `30` | Seconds between overdue-timer sweeps |

## API Usage

### Create a timer

```bash
curl -s -X POST http://localhost:8000/timer \
  -H "Content-Type: application/json" \
  -d '{"hours": 0, "minutes": 1, "seconds": 30, "url": "https://example.com/hook"}' | jq
```

### Get timer status

```bash
curl -s http://localhost:8000/timer/<timer-uuid> | jq
```

---

## Running Tests

```bash
# 1. Start infrastructure
docker compose up postgres redis -d

# 2. Install dev dependencies
uv sync --dev

# 3. Run tests
uv run pytest -v
```

---

## Scaling

```bash
# Run 4 parallel Celery workers
docker compose up --scale worker=4
```

Multiple API instances can be load-balanced (they are stateless).
Only **one** Beat instance should run (it is the sweep coordinator).

---

## Assumptions

- Timers may be scheduled at most **30 days** into the future.
- Webhook targets accept **POST** with a JSON body `{"id": "<uuid>"}`.
- Webhooks are called with a **10-second timeout**.
- Failed webhooks are retried **3 times** with exponential back-off before
  being marked `FAILED`.
- The sweep interval is **30 seconds** (maximum extra latency after a
  broker failure / restart).

---

## High-Traffic Production Changes

For **100+ timer creations per second**:

| Area | Change |
|---|---|
| **DB writes** | PgBouncer connection pool in front of PostgreSQL |
| **DB reads** | Read replicas for `GET /timer/{id}` |
| **Sweep efficiency** | Range-partition `timers` by `scheduled_at`; sweep hits only the current partition |
| **Broker HA** | Redis Sentinel / Cluster, or switch to RabbitMQ / SQS |
| **Workers** | Auto-scale Celery workers by queue depth (KEDA / custom) |
| **Old data** | Archive `executed` / `failed` timers older than N days to cold storage |
| **Observability** | Prometheus metrics: creation rate, webhook latency, sweep lag, retry rate |
| **Rate limiting** | Protect `POST /timer` with token-bucket rate limiter |

