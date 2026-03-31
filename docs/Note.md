# High-Traffic Considerations (100 req/s)

## What 100 req/s means concretely

```text
100 POST /timer per second
  → 100 DB INSERTs/s
  → 100 Celery tasks enqueued/s
  → N webhook POSTs when those timers eventually fire
```

---

## What already handles it in the current architecture

| Component | Why it scales |
|-----------|---------------|
| **FastAPI + asyncpg** | Fully async — 100 concurrent requests don't block each other. Each request is just an `INSERT` + Redis enqueue. |
| **Celery + Redis** | Redis handles millions of ops/s — enqueuing 100 tasks/s is trivial. |
| **`SELECT FOR UPDATE`** | Exactly-once guarantee survives horizontal scaling — multiple workers can't double-fire the same timer. |
| **Recovery sweep** | Timers survive broker/process restarts — durability is already built in. |

---

## The bottlenecks

### 1. PostgreSQL connection limit (most critical)

```text
Default PostgreSQL max_connections = 100

Current pool per API instance:
  pool_size=20 + max_overflow=10 = 30 connections

At 3 API instances:  3 × 30 =  90 connections → approaching the limit
At 5 API instances:  5 × 30 = 150 connections → exceeds limit → 500 errors
```

### 2. Celery worker throughput

```text
--concurrency=4 → 4 webhooks firing simultaneously per worker
If 1000 timers expire at the same second → large backlog builds up
```

### 3. Sweep query under load

```sql
-- Without an index this is a full table scan at scale
SELECT * FROM timers WHERE status = 'pending' AND scheduled_at <= now()
```

---

## Changes needed for 100 req/s production

### 1. PgBouncer — the most important change

Add a connection pooler in front of PostgreSQL. It lets thousands of
app-level connections share a small number of actual DB connections:

```text
API instance 1 (30 conns) ──┐
API instance 2 (30 conns) ──┤──▶ PgBouncer (10 real DB conns) ──▶ PostgreSQL
API instance 3 (30 conns) ──┘
```

With PgBouncer, reduce `pool_size` per instance:

```text
5 instances × 10 connections × (1000ms / 5ms per INSERT) = 10,000 req/s capacity
```

### 2. Move pool sizes to config

Make `pool_size` and `max_overflow` tunable via env vars — no code
changes needed when scaling:

```python
# configs/database.py
pool_size: int = 5
max_overflow: int = 5
pool_size_sync: int = 2
max_overflow_sync: int = 3
```

```python
# database.py
async_engine = create_async_engine(
    settings.db.async_url,
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
)
```

### 3. Scale horizontally via Docker Compose

```bash
docker compose up --scale backend=3 --scale worker=4
```

No code changes required — `SELECT FOR UPDATE` already prevents
duplicate webhook delivery across multiple workers.

### 4. Add a partial index on the sweep query

```sql
CREATE INDEX idx_timers_status_scheduled_at
    ON timers (status, scheduled_at)
    WHERE status = 'pending';
```

### 5. Load balancer in front of API instances

Add nginx or Caddy in front of multiple `backend` instances.

---

## Summary

The architecture is already correct for horizontal scaling.
The required changes are **operational**, not design changes:

| Change | Impact |
|--------|--------|
| PgBouncer | Prevents DB connection exhaustion |
| Configurable pool sizes | Tune without code changes |
| `--scale worker=N` | Absorbs webhook backlog |
| Partial index on timers | Fast sweep queries at any table size |
| Load balancer | Distributes 100 req/s across API instances |
