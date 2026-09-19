# ARGUS

**Human oversight for agent training data.** A full-stack platform for ingesting LLM agent trajectories, coordinating human annotation, retaining provenance, and requiring independent review before examples become eligible for training datasets.

![ARGUS operational dashboard](docs/screenshots/overview.png)

## Start the complete local stack

Requires Docker Desktop (running) and Docker Compose.

```sh
docker compose up --build -d
```

Open **http://localhost:8080**. API documentation: **http://localhost:8000/docs**. The backend applies Alembic migrations and seeds the demo automatically. Health checks coordinate startup for PostgreSQL, Redis, API, and frontend.

| Role | Email | Demo password |
| --- | --- | --- |
| Admin | `admin@argus.dev` | `Argus-demo-2026!` |
| Annotator | `annotator@argus.dev` | `Argus-demo-2026!` |
| Reviewer | `reviewer@argus.dev` | `Argus-demo-2026!` |
| Second annotator | `annotator2@argus.dev` | `Argus-demo-2026!` |

These are explicit local demo accounts. Ports bind to localhost. Copy `.env.example` to `.env` to customize settings; use a generated JWT secret and disable `SEED_DEMO` before a non-demo deployment. Existing seed accounts are never reset when containers restart.

```sh
docker compose ps
docker compose logs -f backend
docker compose down             # stop; preserve data volumes
```

## Try the feedback loop

1. Sign in as admin. Explore the live overview, three projects, and 54 realistic tasks. Filter the task explorer, open a trace, expand tool inputs/outputs, and inspect its audit log.
2. Sign in as an annotator. Open **Annotation Queue**, resume or claim a task, select an outcome and quality score, and write feedback. Structured fields accept a JSON object. Save the draft, then complete the assignment.
3. The task moves to **PENDING_REVIEW**. Sign in as reviewer, find it in the task explorer, inspect the trace and annotations, and select **Review task**. Approval/rejection requires a written rationale.
4. Admins can requeue rejected work. Earlier assignments, annotations, and decisions remain available as provenance.

An annotator cannot approve their own task, including when that annotator is an admin. Completing an annotation never approves it. Dataset exports and advanced monitoring are deliberately future-phase routes.

## Implementation

```text
backend/
  app/
    api/             Auth, projects, tasks, annotations, operations
    auth/            Argon2 and JWT validation
    core/            Typed environment configuration
    db/              Session and transaction management
    models/          Relational entities, enums, constraints
    schemas/         Pydantic input contracts
    repositories/    Tenant-scoped queries and aggregates
    services/        Ingestion and workflow logic
    queue/           Redis priority coordination and fallback
    tests/           API, queue, and PostgreSQL concurrency tests
    seed.py
    main.py
  alembic/           Versioned schema migration
frontend/
  src/components/    Shared UI primitives and trajectory timeline
  src/pages/         Dashboard, projects, explorer, annotation, settings
  e2e/               Browser tests against the real running stack
infrastructure/
  scripts/           Verification and migration checks
  examples/          Ingestion request examples
docs/
  architecture.md
  screenshots/
```

Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic, PostgreSQL 16, Redis 7, and pytest power the backend. React, TypeScript, Vite, Tailwind CSS, TanStack Query, and React Router power the frontend. Nginx serves the production web build and proxies `/api` to FastAPI.

PostgreSQL owns queue/assignment state. A Redis sorted set provides atomic priority hints; `FOR UPDATE SKIP LOCKED`, per-user serialization, and a partial unique index prevent duplicate active ownership. Missing or unavailable Redis entries fall back to PostgreSQL. Assignment leases expire after 60 minutes and recover on the next claim request. See [architecture decisions and failure semantics](docs/architecture.md).

## Local development

Requires Python 3.12+, Node 22+, and the database/cache services. The API reads `.env` from its working directory.

```sh
cp .env.example .env
docker compose up -d postgres redis
# If the complete stack is running, release ports used by local processes:
docker compose stop backend frontend

cd backend
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
pip install -e '.[dev]'
cp ../.env .env
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite forwards `/api` to port 8000. Production and development use the same relative API URLs.

## Environment variables

| Variable | Purpose | Local default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection | See `.env.example`; Compose overrides hostname |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose database initialization | `argus`, `argus`, `argus-local-password` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `JWT_SECRET` | HS256 secret, at least 32 characters | Explicit demo-only value in Compose |
| `TOKEN_MINUTES` | Access-token lifetime | `480` |
| `ASSIGNMENT_TIMEOUT_MINUTES` | Assignment lease duration | `60` |
| `CORS_ORIGINS` | JSON array of allowed browser origins | Local ports 5173 and 8080 |
| `SEED_DEMO` | Seed on container startup | `true` in local Compose |
| `SEED_PASSWORD` | Password for initial demo accounts | `Argus-demo-2026!` |

The seed command requires `SEED_PASSWORD` and does not print it. It creates demo records only when the demo admin does not already exist. To initialize an empty workspace, set `SEED_DEMO=false` and register through the UI. Public registration creates a separate organization; admins provision existing-workspace members through Settings.

## API structure

All protected requests use `Authorization: Bearer <access_token>`. `/docs` contains complete request schemas. Errors have the shape `{"error":{"code":"HTTP_409","message":"..."}}`; validation errors include field details.

| Area | Endpoints |
| --- | --- |
| Identity | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Team | `GET /users`, admin-only `POST /users` |
| Projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` |
| Ingestion | `POST /projects/{id}/tasks`, `POST /projects/{id}/tasks/batch`, `POST /tasks/{id}/runs` |
| Exploration | `GET /tasks`, `GET /tasks/{id}`, `GET /tasks/{id}/trajectory`, `GET /tasks/{id}/audit` |
| Queue | `POST /tasks/{id}/queue`, `POST /annotation/next`, `GET /annotation/assignments`, `GET /annotation/assignments/{id}` |
| Annotation | `POST /assignments/{id}/start`, `POST /assignments/{id}/annotations`, `PATCH /annotations/{id}`, `POST /assignments/{id}/complete` |
| Review | `POST /tasks/{id}/review` with `decision` and `reason` |
| Operations | `GET /overview`, `GET /health` |

`GET /tasks` accepts `project_id`, `status`, exact numeric `priority`, `search`, `sort` (`created_at`, `priority`, `status`), `direction`, `page`, and `page_size`. Queue claims and overview accept an optional `project_id`.

Task ingestion is idempotent for an identical `(project_id, external_id)` payload. Conflicting content returns 409. Batches contain at most 100 tasks and commit atomically. Run ingestion requires strictly increasing unique sequence numbers; it accepts up to 1,000 steps and preserves tool arguments/results and metadata. Queueing requires a trajectory and freezes the trace. Run uploads do not have an idempotency key.

Example payloads: [task](infrastructure/examples/task.json), [agent run](infrastructure/examples/run.json). Using a token and project/task ID from the API:

```sh
curl -X POST "http://localhost:8000/projects/$PROJECT_ID/tasks" \
  -H "Authorization: Bearer $ARGUS_TOKEN" -H 'Content-Type: application/json' \
  --data-binary @infrastructure/examples/task.json

curl -X POST "http://localhost:8000/tasks/$TASK_ID/runs" \
  -H "Authorization: Bearer $ARGUS_TOKEN" -H 'Content-Type: application/json' \
  --data-binary @infrastructure/examples/run.json

curl -X POST "http://localhost:8000/tasks/$TASK_ID/queue" \
  -H "Authorization: Bearer $ARGUS_TOKEN"
```

## Migrations and tests

```sh
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m 'describe change'
.venv/bin/pytest -q
.venv/bin/ruff check app alembic
```

Portable API tests use isolated SQLite databases with foreign keys. Real PostgreSQL tests verify simultaneous claims and same-user duplicate requests. Set both variables below to run the entire API suite against PostgreSQL as well. Tests create/drop isolated randomly named schemas, leaving application tables intact:

```sh
cd backend
TEST_POSTGRES_URL='postgresql+psycopg://argus:argus-local-password@localhost:5432/argus' \
TEST_API_POSTGRES_URL='postgresql+psycopg://argus:argus-local-password@localhost:5432/argus' \
.venv/bin/pytest -q
```

Frontend checks:

```sh
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
npm run format:check
npm run test:e2e
```

Browser tests target the running seeded stack at `http://localhost:8080`, use installed Chrome on macOS, and write screenshots into `docs/screenshots`. Override `ARGUS_WEB_URL`, `CHROME_PATH`, and `SEED_PASSWORD` as needed. The workflow test creates its own organization/users/project and deletes its project afterward; test accounts remain isolated from the demo organization. For Linux CI, install Playwright Chromium and set `CHROME_PATH` to its executable.

From the repository root:

```sh
./infrastructure/scripts/check.sh
./infrastructure/scripts/migration-check.sh
docker compose config --quiet
```

The migration check creates a disposable database, verifies upgrade and metadata consistency, downgrades to base, upgrades again, and removes that database.

## Scope

Phase 1 includes core ingestion, queue recovery, annotation, audit logging, team provisioning, and an independent review gate. It does not yet provide dataset snapshots/exports, external object storage, reviewer consensus/calibration, SSO, or Prometheus/Grafana integration. The local stack is a complete portfolio/development deployment; production deployment should supply managed secrets, TLS, backups, and edge authentication abuse controls.
