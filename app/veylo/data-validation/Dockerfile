FROM python:3.11-slim

# Prevent python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable package management
COPY --from=ghcr.io/astral-sh/uv:0.6.5 /uv /bin/uv

# Copy dependency specifications
COPY pyproject.toml requirements.txt ./

# Install dependencies into system environment
RUN uv pip install --system -r requirements.txt

# Copy application source code
COPY . .

# Ensure entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Expose standard Cloud Run port
EXPOSE 8080

# Execute entrypoint (handles Alembic migrations and launches uvicorn)
ENTRYPOINT ["/app/entrypoint.sh"]
