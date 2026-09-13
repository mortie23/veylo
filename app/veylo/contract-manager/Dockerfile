FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:0.6.5 /uv /bin/uv

# Copy dependency specifications
COPY requirements.txt ./

# Install dependencies into system environment
RUN uv pip install --system -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8080

# Production web server using Gunicorn
CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 120 app:app
