You are a Senior Backend Engineer reviewing and improving a SQLAlchemy timer model for a webhook/timer system.

Goal:
Refactor the `Timer` model and related state design so it is correct, concurrency-safe, readable, and strong enough for this assignment, without overengineering it.
First tell me which of the following improvements worth making:

Important scope:
- Keep the design centered on a single `timers` table
- Do NOT introduce a separate `TimerExecution` / `Execution` table unless it is absolutely necessary
- Prefer the simplest design that still supports:
  - restart recovery
  - horizontal scalability
  - each timer firing only once
- Keep the solution practical and assignment-focused, but production-minded

Context:
- Python 3.14
- SQLAlchemy 2.x typed ORM
- Postgres-style assumptions
- The system schedules timers that later trigger webhooks
- Correctness and clarity matter more than cleverness
- Code should stay readable and simple

Current model characteristics:
- `Timer` has: `id`, `url`, `scheduled_at`, `executed_at`, `status`
- `status` is an enum
- There is a `StateMixin` with `_state_field` and `_allowed_transitions`
- There is an index on `(status, scheduled_at)`

Please improve the design based on these considerations:

1. Add database constraints, not only Python rules
- Enforce important invariants at the DB level, not only in Python.
- Add `CheckConstraint` rules for status/timestamp consistency.
- Example direction:
  - `PENDING` => `executed_at IS NULL`
  - `PROCESSING` => `executed_at IS NULL`
  - `EXECUTED` => `executed_at IS NOT NULL`
  - `FAILED` => define explicit timestamp consistency as well
- Keep the constraint readable and properly named.

2. Introduce `PROCESSING` as an intermediate state
- Expand the state model beyond only `PENDING`, `EXECUTED`, and `FAILED`
- Use transitions like:
  - `PENDING -> PROCESSING`
  - `PROCESSING -> EXECUTED`
  - `PROCESSING -> FAILED`
- The lifecycle should be suitable for worker-based claiming and exactly-once firing logic.

3. Add only the most useful operational metadata
- Add fields that are useful without overcomplicating the model, such as:
  - `failed_at`
  - `last_error`
  - `attempt_count`
  - optionally `processing_started_at` or `claimed_at`
- Only add `max_attempts` or `next_retry_at` if they still fit a simple one-table design.

4. Consider database defaults in addition to Python defaults
- Keep Python defaults where useful, but also add server-side defaults where appropriate.
- At minimum, consider a DB-level default for `status`.
- Use a clean, explicit SQLAlchemy approach.

5. Keep URL validation boundaries clear
- Keep `url` as a DB column, but make it clear that URL validation belongs in the application/domain layer.
- The model should stay simple.
- Do not over-engineer URL parsing in the ORM model.

6. Make nullability explicit
- For nullable columns like `executed_at`, write `nullable=True` explicitly.
- Prefer explicitness over relying on inference.

7. Preserve efficient overdue processing
- Keep the `(status, scheduled_at)` index.
- Ensure the design supports queries such as:
  - `WHERE status = 'pending' AND scheduled_at <= now() ORDER BY scheduled_at ASC LIMIT ...`
- Optimize for predictable worker scans.

8. Stay compatible with a timestamped `BaseModel`
- Assume `BaseModel` may provide `created_at` and `updated_at`.
- Ensure the final model fits cleanly with a base model that provides timezone-aware timestamps and proper defaults.
- Mention assumptions briefly if needed.

9. Keep transition rules in the model, but do not treat them as sufficient alone
- Preserve `_state_field` and `_allowed_transitions`
- Design them cleanly
- Make it clear that model-level transitions complement, but do not replace, DB row locking / worker coordination

10. Keep enum persistence stable and migration-friendly
- Continue using enum `.value` rather than enum names if appropriate
- Keep the enum mapping explicit and readable
- Avoid fragile enum persistence choices

11. Improve `__repr__`
- Make `__repr__` more useful for debugging
- Include at least `id`, `status`, and `scheduled_at`
- Keep it concise

12. Be careful with idempotency/delivery fields
- Since this timer may trigger external webhooks, think ahead about fields like:
  - `delivery_key`
  - `dispatched_at`
  - `webhook_response_code`
  - `webhook_attempts`
- However, do not add these unless they clearly fit the assignment-focused one-table design
- Prefer to defer them rather than overcomplicate the model

Additional architectural guidance:
- Keep the `Timer` model as the main source of truth
- Design it so repository/service code can safely claim timers under concurrency
- The model should support a one-table approach that works with:
  - row locking
  - a `PROCESSING` state
  - restart recovery
  - exactly-once firing semantics at the application level
- Avoid introducing a second table just for theoretical completeness

Output requirements:
- Return the improved `Timer` model code
- Keep the code production-oriented but not overcomplicated
- Use SQLAlchemy 2.x typed ORM style
- Keep naming clean and explicit
- Add short comments only where they improve clarity
- After the code, include:
  1. a brief explanation of the design decisions and trade-offs
  2. why a single-table design is sufficient here
  3. which fields or tables you would defer for a more advanced production version
  4. migration implications, especially enum changes, new constraints, and new columns

Important:
- Prefer simple, maintainable code
- Do not add unnecessary abstractions
- Do not introduce a separate execution table unless you can justify it as strictly necessary
- Do not remove readability for the sake of completeness
- Make choices like a senior backend engineer who understands worker concurrency, but also knows how to avoid overengineering