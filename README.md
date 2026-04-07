# Timer Service

Welcome to my In-Hurry Implementation of the Timer Service ;)

A scalable webhook scheduling service built with
**FastAPI · Celery · Postgresql · Redis**.

See [docs/solution_desing.md](docs/solution_desing.md) for the full design write-up.


There are a few additional improvements I would consider in a next iteration, but based on my own time estimate for the assignment, I chose to prioritize delivering a solid and complete core solution.

---

## Architecture

```text
                LAYER 1 — DURABILITY               LAYER 2 — PRECISION
            ┌────────────────────────┐          ┌─────────────────────────┐
            │      Postgresql        │          │     Redis  +  Celery    │
POST /timer─▶  (source of truth)    │──dispatch─▶  (timely delivery)     │
            │                        │          │                         │
            └───────────┬────────────┘          └────────────┬────────────┘
                        │                                    │
                        │ dispatch (every 5 min)             │ fire at ETA
                        │ sweep (every 60 s)                 │
                        │ ◀─── Celery Beat ──────────────────┘
                        │     (dispatch + recovery)          │
                        │                                    ▼
                        │                              POST webhook
                        │                                    │
                        └────────────────────────────────────┘
                          UPDATE status = 'executed'
```

### Visual Diagram

Editable and shareable versions:

- [Excalidraw source](docs/webhook-scheduler.excalidraw)
- [SVG export](docs/webhook-scheduler.svg)
- [PNG export](docs/webhook-scheduler.png)
- [Open in Excalidraw](https://excalidraw.com/#json=pK7Fl0v2NO3CVn1t7sdH5,FglgSh9OEXgbiqEdiBvYyg)

![Webhook Scheduler Diagram](docs/webhook-scheduler.svg)

| Concern | How it is solved |
|---|---|
| **Persistence** | Postgresql stores every timer before it enters the broker |
| **Precision** | Celery `apply_async(eta=…)` executes near the scheduled instant |
| **Future scheduling** | Beat dispatches `pending` timers due in the next 5 minutes |
| **Duplicate dispatch** | `dispatched_at` column — Beat and API stamp it on first dispatch; query filters `WHERE dispatched_at IS NULL` |
| **Restart recovery** | Beat sweeps every 60 s for overdue `pending` timers and `processing` timers older than the stale threshold |
| **Exactly-once** | `SELECT … FOR UPDATE` + state check inside `fire_webhook` |
| **Horizontal scale** | Stateless API replicas · competing Celery workers |
| **Retry** | Exponential back-off (5 s → 10 s → 20 s), then `FAILED` |

### Project structure

```
src/
├── main.py                    FastAPI app + lifespan
├── core/
│   ├── configs/               Pydantic settings
│   └── database.py            Async + Sync SQLAlchemy engines
├── models/
│   ├── base.py                Declarative base + common fields
│   └── timer.py               Timer ORM model
├── schemas/
│   ├── timer_create_request.py  Pydantic request DTO
│   ├── timer_create_response.py Pydantic response DTO (create)
│   └── timer_retrieve_response.py Pydantic response DTO (get)
├── repository/
│   └── timer.py               TimerRepository (async) + SyncTimerRepository
├── services/
│   ├── timer.py               TimerService — business logic
│   └── webhook.py             Outbound webhook delivery
├── routers/
│   └── timers.py              POST /timer · GET /timer/{id}
└── worker/
    ├── celery_app.py           Celery configuration
    └── tasks.py                dispatch_upcoming_timers · sweep_overdue_timers · fire_webhook
```

### Layer dependency flow

```
Router  →  Service  →  Repository  →  SQLAlchemy Session  →  Postgresql
              ↓
         Celery Task dispatch
```

---

## Quick Start

```bash
# 1. Copy environment template
cp .env.example .env          # edit if needed

# 2. Build and start everything
# Compose will run the one-shot `migrate` service before app containers.
docker compose up --build

# API:   http://localhost:8000
# Docs:  http://localhost:8000/docs
```

## Make Commands

```bash
# Show available targets
make help

# Start only Postgres and Redis
make infra

# Apply database migrations
make migrate

# Run the API locally
make run

# Run a Celery worker locally
make worker

# Run Celery Beat locally
make beat

# Run the full Docker Compose stack
make up

# Stop the Docker Compose stack
make down

# Run tests
make test

# Run lint checks
make lint

# Format code
make fmt

# Remove volumes and reset local data
make clean
```

## Configuration

All settings come from environment variables (or a `.env` file).
Nothing is hardcoded — each domain has its own prefix:

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | — | Postgresql hostname |
| `POSTGRES_PORT` | `5432` | Postgresql port |
| `POSTGRES_USER` | — | Postgresql username |
| `POSTGRES_PASSWORD` | — | Postgresql password |
| `POSTGRES_DB` | — | Database name |
| `REDIS_HOST` | — | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database index |
| `WEBHOOK_TIMEOUT` | `10` | HTTP timeout per webhook call (seconds) |
| `WEBHOOK_MAX_RETRIES` | `3` | Retry attempts before marking `failed` |
| `APP_DISPATCH_WINDOW` | `300` | Timers due within this window are sent to Celery immediately |
| `APP_DISPATCH_INTERVAL` | `300` | Seconds between Beat scans for the next dispatch window |
| `APP_SWEEP_INTERVAL` | `60` | Seconds between overdue-timer recovery sweeps |
| `APP_PROCESSING_STALE_THRESHOLD` | `120` | Seconds before a `processing` timer is considered stuck and re-dispatched |

## API Usage

### Create a timer

```bash
curl -s -X POST http://localhost:8000/timer \
  -H "Content-Type: application/json" \
  -d '{"hours": 0, "minutes": 1, "seconds": 30, "url": "https://httpbin.org/post"}' | python3 -m json.tool
```

### Get timer status

```bash
curl -s http://localhost:8000/timer/<timer-uuid> | python3 -m json.tool
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
- Timers due within the next **5 minutes** are pushed to Celery immediately and stamped with `dispatched_at`.
- Beat scans Postgres every **5 minutes** for newly eligible future timers (`WHERE dispatched_at IS NULL`).
- The overdue recovery sweep runs every **60 seconds**; `processing` timers are only re-dispatched after **120 seconds** (stale threshold) to avoid contending with active workers.

## Delivery Semantics

Webhook delivery at the network boundary should be treated as `at-least-once`, not mathematically exact once.

To make duplicate delivery safe, every outbound webhook includes:

- `Idempotency-Key: <timer_id>`
- `X-Timer-Id: <timer_id>`

The receiving system should deduplicate by that stable key. A common pattern is a `processed_events[already mentioned as executions table]` 
table with a unique `event_id` or `timer_id` column:

1. insert the incoming `Idempotency-Key`
2. if the insert succeeds, apply the business side effect
3. if the insert conflicts, return `200` and do nothing

That gives effective exactly-once behavior at the business level even if the webhook is retried.

---

## High-Traffic Production Changes

For **100+ timer creations per second**:

| Area | Change                                                                            |
|---|-----------------------------------------------------------------------------------|
| **DB writes** | PgBouncer connection pool in front of Postgresql                                  |
| **DB reads** | Read replicas for `GET /timer/{id}`                                               |
| **Sweep efficiency** | Range-partition `timers` by `scheduled_at`; sweep hits only the current partition |
| **Broker HA** | Redis Sentinel / Cluster, or switch to Kafka / SQS / RabbitMQ                     |
| **Workers** | Auto-scale Celery workers by queue depth (KEDA / custom)                          |
| **Old data** | Archive `executed` / `failed` timers older than N days to cold storage            |
| **Observability** | Prometheus metrics: creation rate, webhook latency, sweep lag, retry rate         |
| **Rate limiting** | Protect `POST /timer` with token-bucket rate limiter                              |
