#!/bin/sh
# Runs only against a newly created, disposable database in the local Compose stack.
set -eu
cd "$(dirname "$0")/../.."
DB_NAME="argus_migration_check_$$"
docker compose exec -T postgres createdb -U argus "$DB_NAME"
trap 'docker compose exec -T postgres dropdb -U argus "$DB_NAME"' EXIT
DB_URL="postgresql+psycopg://argus:${POSTGRES_PASSWORD:-argus-local-password}@postgres:5432/$DB_NAME"
docker compose exec -T -e DATABASE_URL="$DB_URL" backend alembic upgrade head
docker compose exec -T -e DATABASE_URL="$DB_URL" backend alembic check
docker compose exec -T -e DATABASE_URL="$DB_URL" backend alembic downgrade base
docker compose exec -T -e DATABASE_URL="$DB_URL" backend alembic upgrade head
