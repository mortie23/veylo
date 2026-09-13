# Veylo Data Contract Management Portal

A serverless web application hosted on Google Cloud Run for creating, inspecting, and managing data contract specifications, BigQuery bronze layer schemas, and data quality validation rules.

## Architecture

- **Backend**: Python 3.11 / Flask with modular Blueprints (`contracts`, `rules`, `api`).
- **Data Layer**: SQLAlchemy 2.0 ORM with dual-mode storage:
  - **Cloud Mode**: Connects directly to Google Cloud BigQuery dataset `veylo_config` via `sqlalchemy-bigquery` using Application Default Credentials (ADC).
  - **Local Development Mode**: Gracefully falls back to local SQLite (`sqlite:///veylo_contracts.db`) for rapid offline development, pre-seeded with sample contracts.
- **Frontend**: Jinja2 templates styled with a Design System CSS components, badges, cards, breadcrumbs, and tables.
- **Testing Workbench**: Interactive in-browser CSV schema validator simulation.
- **Production Server**: Gunicorn running inside a lightweight Cloud Run Docker container.

## Local Development

### 1. Offline Mode (Local SQLite)

Zero cloud dependencies required. Automatically seeds sample contracts on startup:

```bash
cd app/veylo/contract-manager
uv run python app.py
```
Open your browser at `http://localhost:8080`.

### 2. Live Cloud Mode (GCP BigQuery Dev)

Connect directly to the deployed BigQuery dataset `prj-xyz-dev-veylo-0.veylo_config`:

```bash
# Authenticate your local machine with Google ADC
gcloud auth application-default login

# Run with BigQuery backend enabled
DATA_BACKEND=bigquery GCP_PROJECT_ID=prj-xyz-dev-veylo-0 uv run python app.py
```

### 3. Run Unit Tests

```bash
uv run pytest
```

## Docker Container Build & Run

```bash
# Build image locally
docker build -t veylo-contract-manager .

# Run container locally with SQLite backend
docker run -p 8080:8080 -e DATA_BACKEND=sqlite veylo-contract-manager
```
