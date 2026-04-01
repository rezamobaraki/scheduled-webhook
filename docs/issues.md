# Known Issues

Two dispatch-related bugs that cause duplicate Celery messages.

## 1. Dispatcher re-sends the same timer every 5 minutes

The Beat task `dispatch_upcoming_timers` picks up every `PENDING` timer in the window
— including ones it already sent last cycle. There's nothing in the DB to say
"this timer was already handed to the broker."

## 2. Sweep re-dispatches timers that are still being processed

`sweep_overdue_timers` treats all `PROCESSING` timers as stuck. If a worker is
actively delivering a webhook, the sweep fires a second copy 60 s later anyway.

---

# Fix

One new column and one config value. No new tables, models, or processes.

### What changed

- **`dispatched_at`** (`TIMESTAMP`, nullable) on the `timers` table.  
  Set when a timer is sent to the broker. The dispatcher query now filters
  `WHERE dispatched_at IS NULL`, so it only picks up timers that haven't been sent yet.

- **`processing_stale_threshold`** (default 120 s) in app config.  
  The sweep only re-dispatches a `PROCESSING` timer when its `dispatched_at` is older
  than this threshold — meaning the worker likely crashed. Fresh processing timers
  are left alone.

### Before / after

```
Dispatcher (issue #1)

  Before:  Beat runs → sees PENDING timer → sends to broker (again)
  After:   Beat runs → sees dispatched_at is set → skips ✅

Sweep (issue #2)

  Before:  Sweep runs 60s after dispatch → sees PROCESSING → re-sends
  After:   Sweep runs 60s after dispatch → timer is 60s old, threshold is 120s → skips ✅

  Worker crashes → timer stuck at PROCESSING for 3 min → 180s > 120s → re-dispatches ✅
```

### Files touched

| File | What |
|------|------|
| `src/models/timer.py` | Added `dispatched_at` column |
| `src/core/configs/app.py` | Added `processing_stale_threshold` setting |
| `src/repository/timer.py` | Dispatcher filters on `dispatched_at IS NULL`; sweep splits `PROCESSING` with stale cutoff |
| `src/worker/tasks.py` | Both tasks stamp `dispatched_at` after publishing |
| `src/services/timer.py` | `create_timer` stamps `dispatched_at` on immediate dispatch |
| `migrations/` | One `ADD COLUMN` migration |

---

# Alternative: Transactional Outbox

For a high-traffic production system (100+ creations/sec), the better approach is an
outbox table written in the same DB transaction as the timer. A separate relay process
polls the outbox and publishes to Celery, eliminating the dual-write between Postgres
and Redis.

This wasn't chosen here because the bugs are missing guards, not an architectural
problem. The current two-layer scheduler with `SELECT … FOR UPDATE` and `acks_late`
is sound — adding an outbox, a relay process, and version-based idempotency would be
over-engineering for the scope of this project.