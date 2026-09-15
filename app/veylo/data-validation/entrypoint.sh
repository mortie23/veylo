#!/usr/bin/env bash
set -e

echo "Starting Veylo Data Validation Service..."

# Run database migrations if not explicitly disabled
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Applying BigQuery/Alembic schema migrations..."
    if alembic upgrade head; then
        echo "Alembic migrations applied successfully."
    else
        echo "Warning: Alembic migration failed or was skipped."
    fi
fi

# Seed initial contract metadata if requested
if [ "${SEED_INITIAL_CONTRACTS:-false}" = "true" ]; then
    echo "Seeding initial contract metadata..."
    python scripts/seed_contracts.py || echo "Warning: Contract seeding failed or already present."
fi

echo "Starting uvicorn server on port ${PORT:-8080}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}"
