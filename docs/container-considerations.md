# Container Considerations

Design decisions and best practices applied to the Docker / Docker Compose
setup of the Timer Service.

---

## 1. Multi-stage Dockerfile

| Stage | Purpose |
|-------|---------|
| **builder** | Installs `uv`, resolves dependencies, builds the wheel. Contains compilers and build tooling — **never shipped**. |
| **runtime** | Copies only `.venv` + application code from the builder. Final image has no `uv`, no `pip`, no build headers. |

**Why it matters:** The runtime image is significantly smaller, has a
reduced attack surface, and starts faster.

### Layer ordering for cache efficiency

```dockerfile
COPY pyproject.toml uv.lock ./      # ← rarely changes
RUN  uv sync --frozen --no-dev      # ← cached until lock file changes

COPY src/ src/                      # ← changes often (invalidates only this layer)
```

Dependencies are installed **before** source code is copied. A code-only
change doesn't re-download every package.

---

## 2. Non-root User

```dockerfile
RUN groupadd --system appgroup && \
    useradd  --system --gid appgroup --no-create-home appuser
USER appuser
```

The container process runs as `appuser` (UID ~999), not `root`. If the
application is compromised, the attacker can't modify system files or
escalate to host-level root.

---

## 3. Environment Hardening

| Variable | Value | Effect |
|----------|-------|--------|
| `PYTHONDONTWRITEBYTECODE` | `1` | No `.pyc` files — smaller image, no stale bytecode |
| `PYTHONUNBUFFERED` | `1` | `stdout`/`stderr` flush immediately — logs appear in `docker logs` without delay |

---

## 4. `.dockerignore`

Excludes `.git`, `__pycache__`, `.env`, `tests/`, `docs/`, IDE files, and
the Dockerfile itself from the build context. This:

- Keeps the build context small → faster `docker build`
- Prevents secrets (`.env`) from being baked into the image
- Excludes test code from production images

---

## 5. OCI Metadata Labels

```dockerfile
LABEL org.opencontainers.image.title="Timer Service" \
      org.opencontainers.image.version="1.0.0"       \
      ...
```

Machine-readable metadata for registries, scanners, and orchestrators
(e.g. `docker inspect`, Trivy, Kubernetes).

---

## 6. Healthchecks (per-service in Compose)

Healthchecks are **not** baked into the Dockerfile because the same image
serves three different roles (backend, worker, beat), each requiring a
different probe:

| Service | Probe | Why |
|---------|-------|-----|
| **backend** | `python -c "urllib.request.urlopen('http://localhost:8000/health')"` | HTTP liveness — confirms the ASGI server is accepting requests |
| **worker** | `celery inspect ping --timeout 5` | Confirms the worker is connected to the broker and responsive |
| **beat** | `pgrep -f 'celery.*beat'` | Beat is a scheduler, not a worker — process-alive check is sufficient |
| **postgres** | `pg_isready -U $POSTGRES_USER` | Native Postgres readiness probe |
| **redis** | `redis-cli ping` | Native Redis liveness probe |

---

## 7. Log Rotation

```yaml
x-logging: &json-logging
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"
```

Shared via a YAML anchor across all 5 services. Without rotation, a busy
service can fill the host disk with logs. Each service keeps at most
**50 MB** (5 × 10 MB) of logs.

---

## 8. Graceful Shutdown (`stop_grace_period`)

Graceful shutdown is a **multi-layer concern**:

```
Docker SIGTERM ──▶ Celery warm shutdown ──▶ task_acks_late returns msg to broker
     │                    │                          │
     ▼                    ▼                          ▼
stop_grace_period    finish current task      if worker dies, task re-queued
(docker-compose)     (celery built-in)        (celery_app.py config)
```

| Layer | Where configured | What it does |
|-------|------------------|--------------|
| **Celery app** | `celery_app.py` — `task_acks_late=True`, `task_reject_on_worker_lost=True` | Worker only ACKs **after** task completes. If killed mid-flight, the message returns to Redis. |
| **Celery worker** | Built-in behaviour | On `SIGTERM`, stops consuming new tasks and finishes in-flight ones (warm shutdown). |
| **Docker Compose** | `stop_grace_period: 60s` | Sends `SIGTERM`, waits **60 s** (not the default 10 s), then `SIGKILL`. Gives Celery enough runway. |

**Why Compose is the right place:** `stop_grace_period` is an orchestration
concern — how long the container runtime waits. The application already
handles `SIGTERM` gracefully; Compose just needs to give it enough time.

---

## 9. `init: true` (Tini)

```yaml
init: true
```

Without this, the main process (uvicorn / celery) runs as **PID 1** inside
the container. PID 1 has special kernel behaviour:

- **Signals**: doesn't receive default signal handlers — `SIGTERM` may be
  silently ignored, preventing graceful shutdown.
- **Zombies**: doesn't reap orphaned child processes — they accumulate as
  zombie entries in the process table.

`init: true` injects [Tini](https://github.com/krallin/tini) as PID 1,
which forwards signals correctly and reaps zombies.

---

## 10. Networking

A single named bridge network (`timer-network`) is used for all services:

```yaml
networks:
  timer-network:
    driver: bridge
```

**Why a named network instead of the Compose default:**

- **Isolation**: containers from other Compose projects on the same host
  cannot reach these services.
- **DNS**: all services resolve each other by service name (`postgres`,
  `redis`, etc.) within the network.
- **Self-documenting**: the topology is explicit in the compose file.

**Why not dual networks (frontend / backend)?** This is a pure backend
service with no web frontend. A single network is sufficient and avoids
unnecessary complexity.

---

## 11. Pinned Image Tags

```yaml
postgres: 18.3-alpine
redis:    8.6-alpine
python:   3.14-slim
```

Never use `:latest`. Pinned tags ensure:

- **Reproducible builds** — same image today and next month
- **No surprise breaking changes** from upstream
- **Alpine variants** — minimal base image, smaller attack surface

---

## 12. Scalability

```bash
docker compose up --scale worker=4
```

The `worker` service deliberately has **no `container_name`** so Docker can
create multiple replicas with unique names. Singleton services (`backend`,
`beat`) keep their `container_name` to prevent accidental duplication.

---

## 13. Redis Persistence & Memory

```yaml
command: redis-server --appendonly yes --maxmemory 128mb --maxmemory-policy allkeys-lru
```

- **`appendonly yes`** + named volume → data survives container restarts
- **`maxmemory 128mb`** → bounded memory, no OOM surprises
- **`allkeys-lru`** → evicts least-recently-used keys when full

---


## Decisions Intentionally Omitted

The following are valid production hardening measures but were considered
**out of scope** for this assessment:

| Practice | Why omitted |
|----------|-------------|
| `read_only: true` + `tmpfs` | Adds complexity (writable exceptions needed). Appropriate for high-security environments. |
| `cap_drop: ALL` + `security_opt: no-new-privileges` | Defence-in-depth, but noisy for a 5-service demo. |
| `deploy.resources` (CPU/memory limits) | Useful in production orchestrators (Swarm/K8s). Adds verbosity without demonstrating core assignment logic. |
| Dual networks (frontend/backend with `internal: true`) | No frontend exists in this project — a single bridge network is sufficient. |
| TLS between services | Would require certificate management; overkill for local Docker Compose. |
