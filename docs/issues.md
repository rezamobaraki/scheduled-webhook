# Known Issues & Resolution Plan

## Problems

### 1. Dispatcher sends duplicates every 5 minutes

`dispatch_upcoming_timers` runs on Beat every ~5 min and selects all `PENDING` timers
in the window. Because there is no record of "already sent to broker," timers that were
dispatched on the previous Beat cycle (or by the API at creation time) get re-published
to Celery on every pass.

**Root cause:** No `dispatched_at` guard — the query has no way to distinguish
"not yet dispatched" from "dispatched but still pending."

### 2. Sweep re-dispatches PROCESSING timers

`sweep_overdue_timers` selects all `PENDING | PROCESSING` timers whose `scheduled_at`
has passed. A timer that is actively being delivered by a worker (status = `PROCESSING`)
gets re-dispatched immediately, creating unnecessary broker traffic and contention.

**Root cause:** The sweep does not distinguish "active right now" from "stuck after a
worker crash." Any `PROCESSING` timer is treated as overdue.

---

## Chosen Fix — `dispatched_at` + stale threshold

The simplest fix that solves both problems with minimal schema change.

| Problem | Fix |
|---------|-----|
| Duplicate dispatch | Add `dispatched_at` column; filter `WHERE dispatched_at IS NULL` |
| Premature re-dispatch | Only sweep `PROCESSING` timers older than a stale threshold (e.g. 120 s) |

### How it works

```
                    Current behaviour                   With the fix
                    ─────────────────                   ─────────────

Dispatcher:         Timer due at T+3 min                Timer due at T+3 min
                    API dispatches at T=0               API dispatches at T=0, stamps dispatched_at
                    Beat runs at T+1, sees PENDING      Beat runs at T+1, sees dispatched_at IS NOT NULL
                    → sends DUPLICATE message           → SKIPS it ✅

Sweep:              Worker claims timer → PROCESSING    Worker claims timer → PROCESSING
                    Sweep runs 60 s later               Sweep runs 60 s later, checks stale threshold
                    → sends DUPLICATE message           → timer is only 60 s old, threshold is 120 s
                                                        → SKIPS it ✅

                                                        Worker crashes, timer stuck at PROCESSING
                                                        Sweep runs 3 min later, timer is 180 s > 120 s
                                                        → re-dispatches it ✅ (recovery still works)
```

### Change map

| Layer | Change |
|-------|--------|
| **Model** `src/models/timer.py` | Add `dispatched_at: TIMESTAMP(timezone=True), nullable=True` |
| **Config** `src/core/configs/app.py` | Add `processing_stale_threshold: int = 120` |
| **Migration** | One `ADD COLUMN dispatched_at` |
| **Repository** `get_upcoming_pending()` | Add `.where(Timer.dispatched_at.is_(None))` |
| **Repository** `get_overdue_for_update()` | Split `PROCESSING` branch: include only rows where `now - dispatched_at > stale_threshold` |
| **Tasks** `dispatch_upcoming_timers` | Stamp `timer.dispatched_at = now; session.commit()` after `apply_async` |
| **Service** `create_timer` | Stamp `dispatched_at` when dispatching within the window |

~20 lines of logic across 4 files. No new tables, models, or processes.

---

## Alternative Considered — Transactional Outbox

For a production system at high traffic (100+ creations/sec), the stronger approach
would decouple "decide to dispatch" from "publish to Celery" via a transactional outbox:

- An `timer_outbox` table is written in the **same DB transaction** as the timer state
  change, eliminating the DB/broker dual-write.
- A separate **relay process** polls unpublished outbox rows and publishes to Celery.
- A `dispatch_version` column makes duplicate relay publishes idempotent.

### Why it was not chosen

- Introduces a new table, a new model, and a standalone relay process.
- `dispatch_version` concurrency control is harder to test correctly.
- The existing architecture (two-layer scheduler + `SELECT … FOR UPDATE` + `acks_late`)
  is already sound — the bugs are missing guards, not an architectural gap.
- Disproportionate to the scope of the assignment.

The outbox pattern becomes the right call when broker reliability is a hard requirement
or traffic volumes make the dual-write a latency concern.