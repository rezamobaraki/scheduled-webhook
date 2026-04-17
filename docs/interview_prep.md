# Interview Preparation — Scheduled Webhook Timer Service

> Senior Backend Engineer interview Q&A based on the assignment and codebase.

---

## 1. Walk me through the architecture. Why did you choose this design?

**Best Answer:**
I built a **two-layer scheduler**. Layer 1 is PostgreSQL — the durable source of truth. Every timer is persisted before any broker interaction. Layer 2 is Redis/Celery — for precision execution with ETA-based scheduling.

The dispatcher (`dispatch_upcoming_timers`) runs via Celery Beat every 5 minutes, querying Postgres for pending timers within the next window and publishing them to Redis with ETAs. A separate sweep (`sweep_overdue_timers`) every 60 seconds catches anything missed — broker crashes, missed windows, stuck workers.

This means **if Redis dies, no timers are lost** — they're in Postgres and the sweep recovers them. If the process restarts, same thing. The database is the single source of truth; the broker is an optimization for timely delivery.

---

## 2. How do you guarantee exactly-once webhook delivery?

**Best Answer:**
Exactly-once *execution* is achieved through `SELECT ... FOR UPDATE` in `fire_webhook`. When a worker picks up a task, it locks the timer row. It checks the status — if it's already `EXECUTED` or `FAILED`, it skips. If `PENDING`, it transitions to `PROCESSING`, flushes (but doesn't commit, keeping the lock held), delivers the webhook, then commits as `EXECUTED`.

This means a concurrent worker trying the same timer will block on the row lock, then see it's already processed and skip.

For the **webhook receiver's** perspective, I send an `Idempotency-Key` header equal to the timer UUID, so even if we deliver twice (at-least-once semantics), the receiver can deduplicate.

---

## 3. What happens if the application crashes mid-execution?

**Best Answer:**
Several scenarios:
- **Crash before webhook delivery**: Transaction rolls back, timer stays `PENDING`. The sweep picks it up.
- **Crash after webhook delivery but before commit**: Timer stays `PROCESSING`. The sweep has a `stale_threshold` (120s default) — if `dispatched_at` is older than that, it assumes the worker died and re-dispatches. The webhook receiver should use the `Idempotency-Key` to deduplicate.
- **Broker (Redis) dies**: Timers in-flight in Redis are lost, but they're all in Postgres. The sweep catches them as overdue.

`acks_late=True` on the Celery task ensures the broker only removes the message after the task completes successfully.

---

## 4. Why `flush()` instead of `commit()` after claiming the timer?

**Best Answer:**
In `fire_webhook`, after transitioning to `PROCESSING`, I call `session.flush()` instead of `session.commit()`. This writes the status change to the database (making it visible to `FOR UPDATE` contenders) but **keeps the row lock held** through the HTTP delivery. If I committed, another worker could claim the same timer between the commit and the webhook call.

The tradeoff is the DB connection is held for the webhook timeout duration (up to 10s). At scale, I'd switch to **advisory locks** to decouple the row lock from the connection.

---

## 5. How does your system handle horizontal scaling?

**Best Answer:**
- **API servers**: Stateless FastAPI instances behind a load balancer. Timer creation is just a DB write.
- **Celery workers**: Multiple workers can run. `SELECT ... FOR UPDATE` and `skip_locked=True` ensure they don't step on each other. Workers partition work naturally.
- **Celery Beat**: Single instance (SPOF). In production, I'd use `celery-redbeat` to run Beat on multiple nodes with a distributed lock.
- **Database**: Partial indexes (`ix_timers_pending_undispatched`, `ix_timers_overdue_candidates`) ensure the dispatcher and sweep queries stay fast even with millions of rows.

---

## 6. Explain the state machine in your Timer model.

**Best Answer:**
I use a `StateMixin` that enforces allowed transitions: `PENDING → PROCESSING → EXECUTED | FAILED`. The `transition_to()` method raises a `StateTransitionError` if an invalid transition is attempted. This prevents bugs like marking an already-failed timer as executed.

Additionally, the database has a `CHECK` constraint (`ck_timers_status_timestamp_consistency`) that enforces: `EXECUTED` timers must have `executed_at` set, `FAILED` must have `failed_at` set, and `PENDING`/`PROCESSING` must have neither. This is defense-in-depth — the app enforces it, and the DB enforces it independently.

---

## 7. Why did you use the Repository pattern? Isn't it over-engineering for this project?

**Best Answer:**
Two reasons. First, **testability**: unit tests use a `FakeTimerRepository` that implements `TimerAsyncInterface` (a `Protocol`), so they test service logic without touching the database. Second, there are **two separate repository implementations** — `TimerRepository` (async, for FastAPI) and `SyncTimerRepository` (sync, for Celery workers) — because Celery doesn't support async. The interface cleanly separates the two.

`Protocol` is used instead of ABC to keep it lightweight — structural subtyping, no inheritance required.

---

## 8. How do you handle the "dispatched but still pending" problem?

**Best Answer:**
This was a bug discovered during development (documented in `docs/issues.md`). Without deduplication, the dispatcher and sweep would re-dispatch the same timer repeatedly. The fix: a `dispatched_at` column. Once a timer is dispatched, it's stamped and excluded from future dispatcher queries. The sweep only re-dispatches `PROCESSING` timers whose `dispatched_at` is older than the stale threshold — distinguishing "actively being processed" from "worker died."

---

## 9. What about SSRF? The user provides an arbitrary URL.

**Best Answer:**
URLs are validated in the Pydantic schema using a custom validator. It blocks `localhost`, `127.0.0.1`, `0.0.0.0`, private IP ranges (`10.x`, `172.16-31.x`, `192.168.x`), and `169.254.169.254` (AWS metadata). The URL scheme is restricted to `http` and `https`. This prevents attackers from using the service to probe internal infrastructure.

---

## 10. Why Celery over alternatives (APScheduler, asyncio tasks, Kafka)?

**Best Answer:**
- **APScheduler**: Doesn't survive process restarts natively, and its distributed mode is fragile.
- **asyncio tasks**: In-memory only, lost on restart, doesn't scale horizontally.
- **Kafka**: Great for streaming but overkill for delayed task execution — no native ETA/countdown support.
- **Celery**: Battle-tested, ETA support built-in, `acks_late` for crash safety, easy horizontal scaling, and robust retry mechanism. The Redis broker gives sub-second precision for ETA delivery.

---

## 11. What would you change for 100 req/s in production?

**Best Answer:**
- **Batch inserts**: Use `INSERT ... VALUES` batching or `COPY` for bulk timer creation.
- **Connection pooling**: PgBouncer in front of Postgres, tune `pool_size` and `max_overflow`.
- **Partitioned tables**: Partition `timers` by `scheduled_at` (range partitioning by day/week) so old data doesn't slow queries.
- **Dedicated Beat with distributed lock**: `celery-redbeat` for HA Beat.
- **Observability**: Prometheus metrics on queue depth, webhook latency, failure rates. Structured JSON logging with correlation IDs.
- **Rate limiting**: Protect the API with token bucket rate limiting.
- **Worker autoscaling**: Kubernetes HPA based on Redis queue length.

---

## 12. Explain your retry strategy for failed webhooks.

**Best Answer:**
Exponential backoff: `countdown = 2^retries * 5` seconds (5s → 10s → 20s → 40s). Default 3 retries. After exhausting retries, the timer transitions to `FAILED` with `failed_at` set and `last_error` storing the truncated error message (capped at 4096 chars). `acks_late=True` ensures the broker redelivers if the worker crashes during a retry.

---

## 13. How did you approach testing?

**Best Answer:**
Three levels:
- **Unit tests**: `FakeTimerRepository` in-memory, testing service logic (creation, retrieval, not-found). No DB, no network.
- **Schema tests**: Data-driven via `timer_scenarios.json` — 8 valid scenarios and 9+ invalid edge cases (negative values, invalid URLs, SSRF attempts). Parameterized with `pytest.mark.parametrize`.
- **Integration tests**: Real PostgreSQL (spun via Docker), testing the full API through `httpx.AsyncClient`. Task tests mock `WebhookService` to verify Celery task logic with a real DB.

Celery Beat scheduling was not tested — that's Celery's responsibility, not ours.

---

## 14. Why `uuid7` instead of `uuid4`?

**Best Answer:**
UUID v7 is time-ordered — it encodes a Unix timestamp in the most significant bits. This means primary key inserts are sequential, avoiding B-tree page splits and random I/O. For a table that grows continuously with time-based queries, this gives significantly better index performance than random UUID v4. It also allows rough time-based sorting by ID without a secondary index.

---

## 15. What are the known limitations of your solution?

**Best Answer:**
1. **At-least-once delivery**: If the worker crashes after delivering but before committing, the webhook fires again. Mitigated by `Idempotency-Key`.
2. **Single Beat instance**: SPOF for dispatching. Fix: `celery-redbeat`.
3. **DB connection held during webhook**: `flush()` keeps the lock through delivery (up to 10s). Fix: advisory locks.
4. **No authentication/authorization**: The API is open. Production needs API keys or OAuth.
5. **No rate limiting**: Could be DoS'd.
6. **No webhook response logging**: The response status/body from the target URL is not stored.

---

## Testing Questions

### T1. The assignment says "tests are mandatory but sensible testing over 100% coverage." How did you interpret that?

**Best Answer:**
I focused on testing the parts that could silently break in production:

1. **Business logic correctness** — does `time_left` return `0` for expired timers? Does creating a timer persist it and return the right ID?
2. **Exactly-once semantics** — does `fire_webhook` skip an already-executed timer? Does it skip an unknown ID?
3. **Failure path** — does the task retry on webhook failure and eventually mark the timer `FAILED`?
4. **Recovery logic** — does the sweep dispatch overdue pending timers but skip fresh `PROCESSING` ones?
5. **Input validation** — do invalid payloads (negative seconds, private-IP URLs, missing fields) consistently return `422`?

I deliberately did not test Celery Beat's scheduling interval or SQLAlchemy ORM internals — those are the framework's responsibility.

---

### T2. Describe your three levels of tests and why you split them that way.

**Best Answer:**

| Level | Files | What's tested | DB / Broker? |
|---|---|---|---|
| **Unit — service** | `test_service.py` | `TimerService.create_timer`, `retrieve_timer`, not-found | No (fake repo) |
| **Unit — schemas** | `test_schemas.py` | Pydantic validation: valid inputs, negative values, SSRF URLs, missing fields | No |
| **Unit — webhook** | `test_webhook_service.py` | `WebhookService.deliver` HTTP success and failure | Mocked HTTP |
| **Integration — API** | `test_api.py` | Full HTTP → service → real Postgres round-trip | Real Postgres, Celery mocked |
| **Integration — tasks** | `test_tasks.py` | Celery task → real Postgres, `WebhookService` mocked | Real Postgres |

Splitting at this boundary means unit tests run in milliseconds (CI fast-path) and integration tests run against Docker services (full verification). I never mock the database in integration tests — that would hide real SQL bugs.

---

### T3. How does the data-driven testing approach in `timer_scenarios.json` work? Why JSON instead of inline `pytest.mark.parametrize`?

**Best Answer:**
`timer_scenarios.json` holds all valid and invalid input scenarios. The test file reads it once at module load and feeds it directly to `@pytest.mark.parametrize`. Each scenario has an `id`, a `payload`, and an `expected_status`.

Benefits:
- Adding a new edge case (e.g. a new SSRF variant) never requires touching test code — just add an entry to the JSON.
- The `ids` in `pytest.mark.parametrize` come from the JSON's `id` field, so failure output is readable.
- Non-developers (QA, PM) could in theory add scenarios.

The downside is the JSON is not type-checked. In a larger project I'd use a Pydantic model to validate the scenario file itself.

---

### T4. How do you test the `fire_webhook` task without a real Celery broker?

**Best Answer:**
I use `task.apply(args=[...])` — Celery's synchronous "eager" execution. This runs the task inline in the test process, bypassing Redis entirely. No broker, no worker, no network.

`WebhookService` is mocked at the module level with `@patch("src.worker.tasks.webhook_service")`, so the HTTP call never leaves the process. I then assert:
- `mock_service.deliver` was called with the right arguments
- The timer's `status` (re-fetched from the real DB) is `EXECUTED`
- `executed_at` is set, `failed_at` is `None`, `attempt_count == 1`

For the failure path, I set `mock_service.deliver.side_effect = WebhookDeliveryError(...)` and verify `call_count == max_retries + 1` and `status == FAILED`.

---

### T5. How do you ensure test isolation between integration tests?

**Best Answer:**
The `_clean_db` fixture runs `DELETE FROM timers` after every test (autouse, function-scoped). This is faster than truncation with cascade and works for this single-table schema.

The schema itself is created once per test session via the `_create_tables` fixture: it drops and recreates the `public` schema, then runs `alembic upgrade head`. This ensures tests always run against the real migration, not a separately-defined test schema — if a migration is broken, the test suite won't even start.

The `client` fixture injects a fresh `async_session` and overrides FastAPI's dependency, so each test gets a clean HTTP client wired to the test DB.

---

### T6. You mock `fire_webhook.apply_async` in API tests. Doesn't that reduce confidence?

**Best Answer:**
Yes, it's a deliberate tradeoff. The API tests verify the HTTP layer and the DB write. The task tests independently verify the full task execution path. Together they cover the complete flow; neither test needs a live broker.

If I let API tests dispatch to a real broker, tests would be:
- Flaky (race conditions between task execution and assertion)
- Slower (real network + worker latency)
- Harder to isolate (shared broker state between tests)

The integration test `test_dispatches_celery_task` does assert that `mock_fire_webhook.assert_called_once()` — so I still verify the API called the broker correctly, just not the broker's side of it.

---

### T7. How do you test the database `CHECK` constraints?

**Best Answer:**
Directly in `test_tasks.py` — I insert a `Timer` with `status=EXECUTED` and `executed_at=None` (violating the constraint) and assert that `session.commit()` raises `IntegrityError`. Same for `FAILED` without `failed_at`. Then I call `session.rollback()` to restore the session.

This is important because:
1. It proves the DB constraint catches what the application state machine might miss (defense-in-depth).
2. It documents the expected DB-level invariants for future developers.

---

### T8. How would you add a test for the `dispatch_upcoming_timers` periodic task?

**Best Answer:**
It's already tested in `TestDispatcher`. I insert two `PENDING` timers with `scheduled_at` within the 5-minute window, one beyond the window, call `dispatch_upcoming_timers()` directly (eager, no broker), and assert:
- `fire_webhook.apply_async` was called for the two in-window timers
- the far-future timer was NOT dispatched
- `dispatched_at` is stamped on dispatched timers

I also test the negative: an already-dispatched timer (`dispatched_at` already set) is skipped on the next dispatcher run — this is the deduplication guard.

---

## Bonus: Why FastAPI over Django?

**Best Answer:**
FastAPI gives async-native request handling (important for I/O-bound timer creation), automatic OpenAPI docs, Pydantic validation with zero boilerplate, and dependency injection. Django's ORM doesn't support async well with Celery (both async and sync paths were needed), and DRF adds serializer overhead that wasn't required here. FastAPI + SQLAlchemy 2.0 async gave the right balance of performance and flexibility.

---

## Key Topics to Emphasise

| Topic | What to Nail |
|---|---|
| Two-layer architecture | Postgres = durability, Redis = precision |
| Exactly-once semantics | `SELECT FOR UPDATE` + status guard + `Idempotency-Key` |
| Crash recovery | Sweep + stale threshold + `acks_late` |
| Horizontal scaling | Stateless API, `skip_locked`, Beat SPOF + fix |
| State machine | `StateMixin` + DB `CHECK` constraint as defence-in-depth |
| SSRF | URL validation in Pydantic schema |
| Testing strategy | Unit (fake repo) → schema (data-driven) → integration (real DB) |
| Test isolation | `DELETE FROM timers` after each test, `alembic upgrade head` per session |
| Celery task testing | `task.apply()` eager execution, mock `WebhookService`, real Postgres |
| Data-driven tests | `timer_scenarios.json` feeds `parametrize` — code unchanged for new cases |
| DB constraint tests | `IntegrityError` on `EXECUTED` without `executed_at` (defense-in-depth) |
