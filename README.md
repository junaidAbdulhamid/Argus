# ARGUS

**Human oversight for agent training data.** A full-stack platform for ingesting LLM agent trajectories, coordinating human annotation, retaining provenance, and requiring independent review before examples become eligible for training datasets.

![ARGUS operational dashboard](docs/screenshots/overview.png)

## Start the complete local stack

Requires Docker Desktop (running) and Docker Compose.

```sh
docker compose up --build -d
```

Open **http://localhost:8080**. API documentation: **http://localhost:8000/docs**. The backend applies Alembic migrations and seeds the demo automatically. Health checks coordinate startup for PostgreSQL, Redis, API, export worker, and frontend.

| Role | Email | Demo password |
| --- | --- | --- |
| Admin | `admin@argus.dev` | `Argus-demo-2026!` |
| Annotator | `annotator@argus.dev` | `Argus-demo-2026!` |
| Reviewer | `reviewer@argus.dev` | `Argus-demo-2026!` |
| Second annotator | `annotator2@argus.dev` | `Argus-demo-2026!` |
| Third annotator | `annotator3@argus.dev` | `Argus-demo-2026!` |

These are explicit local demo accounts. Ports bind to localhost. Copy `.env.example` to `.env` to customize settings; use a generated JWT secret and disable `SEED_DEMO` before a non-demo deployment. Existing seed accounts are never reset when containers restart.

```sh
docker compose ps
docker compose logs -f backend
docker compose down             # stop; preserve data volumes
```

## Try the feedback loop

1. Sign in as admin. Open the **Agent quality · multi-review** project and its schema/quality settings. It has seven dynamic field types, three independent annotators, and explicit human quality gates.
2. Open **Annotation Queue** as an annotator. Claim work, complete the versioned form, save, and submit. Other annotators' answers remain hidden by default. Reference tasks are inserted at the configured cadence.
3. Open **Human Review** as reviewer. Compare the trajectory, independent annotations, agreement metrics, and history. Approve, reject, request changes, or escalate with a written rationale. Resolve open issues through **Escalations**.
4. Open **Quality** for cohort agreement, gold accuracy, throughput, and inspectable annotator profiles. Agreement measures consistency, not correctness.
5. Open **Datasets → argus-agent-reliability**. The seed includes two finalized versions, full lineage, trajectory exports, and a real paired-response DPO export. To build another version, prepare approved examples, filter/select them, create a draft, and finalize. Finalization rechecks every gate.
6. Request an SFT, DPO, reward, or trajectory export as JSON/JSONL. **Export History** tracks worker progress and offers dataset, manifest, schema, and provenance downloads.

The additive Phase 2 seed includes 18 tasks, three annotators, gold attempts, disagreements, escalations, revisions, five training examples, and two finalized dataset versions. Phase 1's original projects and tasks remain available. A reviewer cannot approve their own annotation. Completing annotations never grants training eligibility. See [quality rules](docs/quality-control.md) and [datasets and export contracts](docs/datasets.md).

## Implementation

```text
backend/
  app/
    api/             Auth, projects, tasks, quality, datasets, operations
    auth/            Argon2 and JWT validation
    core/            Typed environment configuration
    db/              Session and transaction management
    models/          Relational entities, enums, constraints
    schemas/         Pydantic input contracts
    repositories/    Tenant-scoped queries and aggregates
    services/        Workflow, consensus, quality gates, snapshots, exporters
    queue/           Redis coordination, export worker, database fallback
    tests/           API, queue, and PostgreSQL concurrency tests
    seed.py
    main.py
  alembic/           Versioned schema migration
frontend/
  src/components/    Shared UI primitives and trajectory timeline
  src/pages/         Annotation, review, quality, schemas, datasets, lineage
  e2e/               Browser tests against the real running stack
infrastructure/
  scripts/           Verification and migration checks
  examples/          Ingestion request examples
docs/
  architecture.md
  screenshots/
```

Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic, PostgreSQL 16, Redis 7, and pytest power the backend. React, TypeScript, Vite, Tailwind CSS, TanStack Query, and React Router power the frontend. Nginx serves the production web build and proxies `/api` to FastAPI.

PostgreSQL owns queue/assignment state. A Redis sorted set provides atomic priority hints; `FOR UPDATE SKIP LOCKED`, per-user serialization, and a partial unique index prevent duplicate active ownership within each task/annotator/round. Missing or unavailable Redis entries fall back to PostgreSQL. Assignment leases expire after 60 minutes and recover on the next claim request. See [architecture decisions and failure semantics](docs/architecture.md).

## Local development

Requires Python 3.12+, Node 22+, and the database/cache services. The API reads `.env` from its working directory.

```sh
cp .env.example .env
docker compose up -d postgres redis
# If the complete stack is running, release ports used by local processes:
docker compose stop backend worker frontend

cd backend
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
pip install -e '.[dev]'
cp ../.env .env
alembic upgrade head
python -m app.seed
python -m app.seed_phase2
uvicorn app.main:app --reload --port 8000
```

In another terminal, activate the backend environment and run `python -m app.queue.worker`. The API and worker must use the same `EXPORT_DIRECTORY`. Start the frontend separately:

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
| `EXPORT_DIRECTORY` | Shared API/worker artifact directory | `./exports` locally; `/app/exports` in Compose |
| `SEED_PASSWORD` | Password for initial demo accounts | `Argus-demo-2026!` |

The seed command requires `SEED_PASSWORD` and does not print it. Phase 1 skips an existing demo admin; Phase 2 separately skips an existing demo quality project. To initialize an empty workspace, set `SEED_DEMO=false` and register through the UI. Public registration creates a separate organization; admins provision existing-workspace members through Settings.

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
| Quality configuration | `GET/PUT /projects/{id}/quality-rules`, `GET/POST /projects/{id}/annotation-schemas` |
| Human review | `GET /review/queue`, `GET /tasks/{id}/quality`, `POST /tasks/{id}/reviews`, `POST /tasks/{id}/quality-gate` |
| Calibration | `POST /tasks/{id}/gold`, `GET /gold-tasks`, `GET /quality/dashboard` |
| Escalations | `GET /escalations`, `POST /tasks/{id}/escalations`, `POST /escalations/{id}/resolve` |
| Training examples | `POST /tasks/{id}/training-examples`, `POST /training-examples/materialize`, `POST /training-examples/preview`, `GET /training-examples/{id}/lineage` |
| Datasets | `GET/POST /datasets`, `GET /datasets/{id}`, `POST /datasets/{id}/versions`, `GET /dataset-versions/{id}`, `POST /dataset-versions/{id}/finalize` |
| Exports | `POST /dataset-versions/{id}/exports`, `GET /exports`, `GET /exports/{id}/files/{artifact}` |
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

Browser tests target the running seeded stack at `http://localhost:8080`, use installed Chrome on macOS, and write screenshots into `docs/screenshots`. Override `ARGUS_WEB_URL`, `CHROME_PATH`, and `SEED_PASSWORD` as needed. Browser workflows create isolated organizations/users/projects. Unprotected projects are deleted afterward; finalized provenance is intentionally retained in the isolated test organization. For Linux CI, install Playwright Chromium and set `CHROME_PATH` to its executable.

From the repository root:

```sh
./infrastructure/scripts/check.sh
./infrastructure/scripts/migration-check.sh
docker compose config --quiet
```

The migration check creates a disposable database, verifies upgrade and metadata consistency, downgrades to base, upgrades again, and removes that database.

## Scope

Phase 2 delivers versioned annotation schemas, independent multi-annotator work, normalized human reviews, consensus, auditable gates, gold calibration, escalations, immutable dataset versions, full lineage, and background JSON/JSONL exports. Monitoring integrations, external object storage, SSO, and Parquet remain outside this phase. Local artifact storage is a shared Docker volume; large data rows stream during export, while the provenance index is collected in memory. Production deployment should supply managed secrets, TLS, backups, and edge authentication abuse controls.
