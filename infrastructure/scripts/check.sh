#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
(cd backend && .venv/bin/pytest -q && .venv/bin/ruff check app alembic)
(cd frontend && npm run typecheck && npm test && npm run lint && npm run build)
docker compose config --quiet
