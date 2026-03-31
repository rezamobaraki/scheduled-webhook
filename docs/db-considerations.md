# Database & Repository — Design Trade-offs

Key decisions made in the data-access layer and their trade-offs.

---

## 1. `flush()` vs `commit()` in Repositories

| Aspect | `flush()` (chosen) | `commit()` in repo |
|--------|--------------------|--------------------|
| **Transaction boundary** | Owned by the session dependency / caller | Scattered across repo methods |
| **Composability** | Multiple repo calls in one transaction | Each call is its own transaction — no atomicity across calls |
| **Testability** | Easy to wrap in a rollback-only session | Tests must mock or undo committed data |
| **Risk** | Caller *must* commit (forgotten commit = lost data) | Harder to break, but violates Single Responsibility |

**Decision:** Repositories only `flush()`. The FastAPI session dependency
(`get_async_session`) commits on success and rolls back on error. Celery
tasks call `session.commit()` explicitly after the full operation succeeds.

---

## 2. `Session.get()` vs `select()` for Primary-Key Lookups

| Aspect | `Session.get()` (chosen) | `select().where(pk == ?)` |
|--------|--------------------------|---------------------------|
| **Identity-map hit** | Returns cached object instantly — zero SQL | Always round-trips to the database |
| **Readability** | One-liner, semantic ("get by PK") | Verbose, hides intent in a generic query |
| **Flexibility** | PK-only — cannot add filters | Arbitrary WHERE clauses |

**Decision:** Use `Session.get()` for simple PK lookups (e.g. `get_by_id`).
Use `select()` when additional filters are needed (e.g. `get_for_update`
adds `WHERE status IN ('pending', 'processing')`).

---

## 3. `skip_locked=True` on Sweep Queries

| Aspect | `skip_locked` (chosen) | Plain `FOR UPDATE` |
|--------|------------------------|--------------------|
| **Concurrency** | Concurrent sweep workers partition rows automatically — no blocking | Workers queue behind each other on locked rows |
| **Throughput** | Near-linear scaling with worker count | Serialised — adding workers doesn't help |
| **Trade-off** | A skipped row will be picked up on the next sweep cycle (30 s delay) | Every row is processed in order, but slowly |

**Decision:** `skip_locked=True` for the sweep. The 30 s Beat interval
is an acceptable ceiling; throughput under contention matters more.

---

## 4. Injecting `now` vs Calling `datetime.now()` Inside the Repo

| Aspect | Inject `now` (chosen) | `datetime.now()` inside repo |
|--------|----------------------|------------------------------|
| **Testability** | Caller controls the clock — deterministic tests | Must patch `datetime.now` or freeze time |
| **Consistency** | Single timestamp for the entire operation | Slight clock drift between calls |
| **Verbosity** | Slightly more arguments | Slightly less arguments |

**Decision:** `now` is always passed by the caller. It makes tests
straightforward and guarantees a consistent timestamp within an operation.

---

## 5. `SELECT … FOR UPDATE` for Exactly-Once Delivery

| Aspect | Row-level lock (chosen) | Application-level dedup (e.g. Redis lock) |
|--------|-------------------------|-------------------------------------------|
| **Consistency** | DB-native, ACID-guaranteed — impossible to double-fire | Relies on an external system; Redis crash = potential double-fire |
| **Simplicity** | No extra infrastructure | Requires Redis + TTL tuning |
| **Performance** | Minimal overhead for single-row locks | Faster at extreme scale (no DB round-trip) |

**Decision:** `SELECT … FOR UPDATE` keeps the system simple and correct
with zero additional infrastructure. At the scale of this service
(100 req/s), row-level locking adds negligible overhead.

---

## 6. Connection Pooling Configuration

```text
Async (FastAPI):  pool_size=20, max_overflow=10  → 30 connections max per instance
Sync  (Celery):   pool_size=5,  max_overflow=5   → 10 connections max per worker
```

| Concern | Mitigation |
|---------|------------|
| Postgresql default `max_connections = 100` | At 2 API + 2 workers: (2 × 30) + (2 × 10) = 80 — within limits |
| Scaling beyond 3 instances | Introduce PgBouncer as a connection multiplexer |
| Idle connection cost | `pool_recycle=1800` drops stale connections; `pool_pre_ping=True` validates before use |

