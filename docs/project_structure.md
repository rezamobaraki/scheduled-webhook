# Project Structure Reference

> Use this document as a blueprint when scaffolding a new FastAPI service.
> Replace every `timer` / `Timer` / `webhook` reference with your domain concepts.

---

## Tech Stack

| Layer             | Technology                              |
| ----------------- | --------------------------------------- |
| Language          | Python ≥ 3.14                           |
| Framework         | FastAPI + Uvicorn                       |
| ORM / DB          | SQLAlchemy 2 (async + sync) + asyncpg   |
| Migrations        | Alembic (async runner)                  |
| Task Queue        | Celery + Redis broker                   |
| Config            | pydantic-settings (`.env`)              |
| HTTP Client       | httpx                                   |
| Logging           | structlog (JSON)                        |
| Packaging         | uv + hatchling                          |
| Linting / Format  | Ruff                                    |
| Testing           | pytest + pytest-asyncio                 |
| Containers        | Docker multi-stage + Docker Compose     |

---

## Directory Tree

```
project-root/
│
│── pyproject.toml              # Dependencies, build system, tool config (ruff, pytest)
│── uv.lock                     # Lock file (uv)
│── alembic.ini                 # Alembic configuration (points to migrations/)
│── Dockerfile                  # Multi-stage: builder → runtime (non-root user)
│── docker-compose.yml          # Full stack: postgres, redis, backend, worker, beat, migrate
│── Makefile                    # Dev shortcuts: run, worker, beat, test, lint, fmt, migrate, infra, up, down
│── .env                        # Environment variables (not committed)
│── README.md
│
├── docs/                       # Documentation & design artifacts
│
├── data/                       # Static / seed data
│
├── migrations/                 # Alembic migrations
│   ├── env.py                  # Async migration runner (reads settings, imports BaseModel.metadata)
│   ├── script.py.mako          # Migration template
│   └── versions/               # Auto-generated migration files
│       └── *.py
│
├── src/                        # Application package
│   ├── __init__.py             # (empty)
│   ├── main.py                 # FastAPI app, lifespan, router inclusion, exception handlers
│   │
│   ├── core/                   # Cross-cutting infrastructure
│   │   ├── __init__.py         # Re-exports: Logger
│   │   ├── logging.py          # structlog setup (Logger.setup / Logger.get)
│   │   ├── database.py         # Async engine + session factory (FastAPI) & sync engine + session (Celery)
│   │   ├── responses.py        # BaseResponse, ErrorResponse Pydantic models
│   │   │
│   │   ├── configs/            # pydantic-settings config classes
│   │   │   ├── __init__.py     # Settings dataclass aggregating all sub-configs + singleton `settings`
│   │   │   ├── base.py         # BaseConfig(BaseSettings) — env_file=".env", extra="ignore"
│   │   │   ├── app.py          # AppSettings  (APP_ prefix)  — domain-specific knobs
│   │   │   ├── database.py     # DatabaseSettings (POSTGRES_ prefix) — host, port, pool, computed URLs
│   │   │   ├── redis.py        # RedisSettings (REDIS_ prefix) — host, port, computed URL
│   │   │   └── webhook.py      # WebhookSettings (WEBHOOK_ prefix) — timeout, retries
│   │   │
│   │   └── errors/             # Exception hierarchy + FastAPI handlers
│   │       ├── __init__.py     # Re-exports all error classes + register_exception_handlers
│   │       ├── base.py         # AppError(Exception) — status_code, code (ErrorCode enum)
│   │       ├── handlers.py     # register_exception_handlers(app) — maps AppError & ValidationError → JSON
│   │       ├── state.py        # StateTransitionError(AppError) — 409 Conflict
│   │       ├── timer.py        # TimerNotFoundError(AppError) — 404 (replace with your domain)
│   │       └── webhook.py      # WebhookDeliveryError(Exception) — non-HTTP, used in worker
│   │
│   ├── enums/                  # Enum definitions
│   │   ├── __init__.py         # Re-exports
│   │   ├── error_code.py       # ErrorCode(StrEnum) — INTERNAL_ERROR, VALIDATION_ERROR, …
│   │   └── timer_status.py     # TimerStatus(StrEnum) — PENDING, PROCESSING, EXECUTED, FAILED
│   │
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── __init__.py         # Re-exports: BaseModel, Timer
│   │   ├── base.py             # BaseModel(DeclarativeBase) — created_at, updated_at (server-default)
│   │   ├── state_mixin.py      # StateMixin — generic FSM mixin (transition_to, can_transition_to)
│   │   └── timer.py            # Timer(StateMixin, BaseModel) — domain entity w/ table args, indexes, checks
│   │
│   ├── repository/             # Data-access layer (protocol + implementation)
│   │   ├── __init__.py         # Re-exports
│   │   ├── interfaces.py       # Protocol classes (TimerAsyncInterface, TimerSyncInterface)
│   │   ├── timer.py            # TimerRepository (async/FastAPI), SyncTimerRepository (sync/Celery)
│   │   └── execution.py        # (placeholder for additional repo logic)
│   │
│   ├── schemas/                # Pydantic request/response DTOs
│   │   ├── __init__.py         # Re-exports
│   │   ├── timer_create_request.py      # TimerCreateRequest + validators (SSRF protection, duration cap)
│   │   ├── timer_create_response.py     # TimerCreateResponse(BaseResponse)
│   │   └── timer_retrieve_response.py   # TimerRetrieveResponse(BaseResponse)
│   │
│   ├── routers/                # FastAPI routers (thin controllers)
│   │   ├── __init__.py         # Re-exports: timers_router
│   │   └── timers.py           # POST /timer, GET /timer/{id} — injects session → repo → service
│   │
│   ├── services/               # Business logic
│   │   ├── __init__.py         # Re-exports: TimerService, WebhookService
│   │   ├── timer.py            # TimerService — create/retrieve orchestration, conditional dispatch
│   │   └── webhook.py          # WebhookService — synchronous httpx POST delivery
│   │
│   └── worker/                 # Celery application & tasks
│       ├── __init__.py         # (empty)
│       ├── celery_app.py       # Celery() config, broker, beat_schedule, worker_init signal → Logger
│       └── tasks.py            # fire_webhook, dispatch_upcoming_timers, sweep_overdue_timers
│
└── tests/                      # Test suite
    ├── __init__.py
    ├── conftest.py             # Shared helpers (e.g., make_*_payload factories)
    ├── data/                   # Test fixtures / JSON scenarios
    │   └── *.json
    │
    ├── unit/                   # Pure unit tests (no DB, no network)
    │   ├── __init__.py
    │   ├── test_schemas.py
    │   ├── test_service.py
    │   └── test_webhook_service.py
    │
    └── integration/            # Integration tests (needs Postgres + Redis via Docker)
        ├── __init__.py
        ├── conftest.py         # DB lifecycle, async session, Celery mock, httpx AsyncClient
        ├── test_api.py
        └── test_tasks.py
```

---

## Architectural Patterns

### 1. Layered Architecture

```
Router (thin)  →  Service (business logic)  →  Repository (data access)  →  Model (ORM)
       ↑                                              ↑
   Schemas (DTOs)                              Protocol interfaces
```

- **Routers** are thin controllers — they only wire dependencies and delegate.
- **Services** contain business logic; they accept repository _interfaces_ (Protocols), not concrete classes.
- **Repositories** wrap SQLAlchemy queries. Separate async (FastAPI) and sync (Celery) implementations.
- **Models** are plain SQLAlchemy ORM entities.

### 2. Configuration

- One `BaseConfig(BaseSettings)` with `env_file=".env"` and `extra="ignore"`.
- Each sub-config gets its own file and env prefix: `POSTGRES_`, `REDIS_`, `APP_`, `WEBHOOK_`.
- An immutable `Settings` dataclass aggregates them all with a module-level singleton `settings`.

```python
# src/core/configs/__init__.py
@dataclass(frozen=True)
class Settings:
    app: AppSettings
    database: DatabaseSettings
    redis: RedisSettings
    webhook: WebhookSettings

settings = Settings(
    app=AppSettings(),
    database=DatabaseSettings(),
    redis=RedisSettings(),
    webhook=WebhookSettings(),
)
```

### 3. Database

- **Async engine** for FastAPI request path (asyncpg driver).
- **Sync engine** for Celery workers (psycopg driver).
- Session lifecycle managed by a FastAPI dependency (`get_async_session`) that auto-commits / rolls back.
- Alembic migrations use an async runner (`asyncio.run`).

### 4. Error Handling

- `AppError(Exception)` base with `status_code` and `code` (enum).
- Domain errors extend `AppError` (e.g., `TimerNotFoundError` → 404).
- `register_exception_handlers(app)` maps `AppError` → `ErrorResponse` JSON and `RequestValidationError` → 422.
- All error responses share a consistent schema: `{ error, code, details? }`.

### 5. State Machine (FSM)

- `StateMixin` is a reusable mixin for any model with a status field.
- Allowed transitions are declared as a class-level dict.
- `transition_to()` raises `StateTransitionError` on illegal transitions.

```python
class MyModel(StateMixin, BaseModel):
    _state_field = "status"
    _allowed_transitions = {
        Status.DRAFT: {Status.ACTIVE},
        Status.ACTIVE: {Status.COMPLETED, Status.CANCELLED},
    }
```

### 6. Worker (Celery)

- `celery_app.py` — broker config, beat schedule, reliability settings (`acks_late`, `reject_on_worker_lost`).
- `tasks.py` — task definitions; uses sync sessions + `SELECT … FOR UPDATE` for exactly-once semantics.
- `Logger.setup()` called via `worker_init` signal.

### 7. Logging

- `structlog` with JSON rendering + ISO timestamps.
- `Logger.setup()` called once at app startup (lifespan) and worker init.
- `Logger.get(__name__)` per module for structured, contextual logs.

---

## Key Files — What Goes Where

| You need to…                    | Create / edit in…                       |
| ------------------------------- | --------------------------------------- |
| Add a new entity                | `models/<entity>.py`                    |
| Add a new enum                  | `enums/<name>.py`                       |
| Add a new request/response DTO  | `schemas/<entity>_<action>_<type>.py`   |
| Add data access queries         | `repository/<entity>.py`                |
| Add a repository interface      | `repository/interfaces.py`              |
| Add business logic              | `services/<entity>.py`                  |
| Add API endpoints               | `routers/<entity>.py`                   |
| Add background tasks            | `worker/tasks.py`                       |
| Add a config section            | `core/configs/<name>.py`                |
| Add a domain error              | `core/errors/<name>.py`                 |
| Add a DB migration              | `alembic revision --autogenerate -m ""` |

---

## Conventions & Rules

### Naming
- **Files**: `snake_case.py` — one concept per file.
- **Classes**: `PascalCase`.
- **Enums**: `StrEnum` for all status / code enums (serialises cleanly to JSON).
- **`__init__.py`**: every package re-exports its public symbols with `__all__`.

### Dependency Injection
- FastAPI `Depends()` for session injection in routers.
- Repositories injected into services via constructor (not global).
- Services instantiated in routers — no singletons.

### Immutability
- Config is a `frozen=True` dataclass.
- `__slots__` on services and repositories for memory efficiency.

### Testing
- **Unit tests** — pure, no DB, mock repositories via Protocols.
- **Integration tests** — Alembic resets schema per session, truncates per test, overrides FastAPI deps.
- **Celery mocked** in API integration tests via `monkeypatch`.

---

## Docker Architecture

```
┌─────────────┐   ┌──────────┐
│  PostgreSQL  │   │  Redis   │
└──────┬──────┘   └────┬─────┘
       │               │
 ┌─────┴───────────────┴──────┐
 │         migrate             │  (runs once: alembic upgrade head)
 └─────────────────────────────┘
       │               │
 ┌─────┴──────┐  ┌─────┴──────┐  ┌──────────┐
 │  backend   │  │  worker(s) │  │   beat   │
 │ (uvicorn)  │  │  (celery)  │  │ (celery) │
 └────────────┘  └────────────┘  └──────────┘
```

- **Multi-stage Dockerfile**: `builder` (install deps + build wheel) → `runtime` (slim, non-root user).
- **docker-compose.yml**: health-checks on all services, `depends_on` with conditions, JSON logging, graceful stop.
- Workers are scalable: `docker compose up --scale worker=4`.

---

## Makefile Targets

| Target    | Description                          |
| --------- | ------------------------------------ |
| `run`     | Start FastAPI dev server (+ migrate) |
| `worker`  | Start Celery worker (+ migrate)      |
| `beat`    | Start Celery Beat (+ migrate)        |
| `test`    | Run pytest                           |
| `lint`    | Ruff check                           |
| `fmt`     | Ruff format + fix                    |
| `migrate` | Alembic upgrade head                 |
| `infra`   | Start Postgres + Redis in Docker     |
| `up`      | Full Docker Compose stack            |
| `down`    | Stop all services                    |
| `clean`   | Stop + remove volumes                |

---

## How to Bootstrap a New Project

1. **Copy the skeleton** — duplicate the directory tree above.
2. **Rename** — replace `timer-service` in `pyproject.toml`, `docker-compose.yml`, `Dockerfile` labels.
3. **Define your domain** — create enums, models, schemas, repository, service, router.
4. **Wire it up**:
   - Add router to `main.py` via `app.include_router(...)`.
   - Add error classes and register in `core/errors/__init__.py`.
   - Add config section if needed in `core/configs/`.
5. **Create migration** — `uv run alembic revision --autogenerate -m "create <table>"`.
6. **Add tests** — unit tests for schemas/services, integration tests for API + tasks.
7. **Run** — `make infra && make run` (dev) or `make up` (full Docker stack).

