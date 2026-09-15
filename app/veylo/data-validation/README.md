# Veylo Data Contract Validation Engine

A serverless validation engine hosted on Google Cloud Run that validates uploaded data files (CSV/XLSX) against data contracts defined in BigQuery (`veylo_config`), ingests validated data into BigQuery bronze tables (`veylo_bronze`), and reports validation status and row-level errors back to Microsoft Dataverse via OData Web API.

## Architecture

See [docs/DATA_VALIDATION_WAREHOUSE.md](../../../docs/DATA_VALIDATION_WAREHOUSE.md) for full design specification.

- **FastAPI / Cloud Run**: Receives webhook requests on `POST /validate`, acknowledges with `202 Accepted`, and processes validations asynchronously in background tasks.
- **BigQuery Metadata**: Stores contracts, entities, attributes, code management mappings, and data quality rules in `veylo_config`.
- **Validation Engine**: Performs column mapping, nullability checks, type casting, code set lookups, and regex/range/length DQ rules.
- **BigQuery Warehouse**: Auto-creates target tables and loads valid data into `veylo_bronze` with `WRITE_TRUNCATE`.
- **Dataverse Callback**: Pushes status updates (`Processed` or `Failed`) and row-level errors (`vey_FileIngestionError`) back to Dataverse using Entra ID OAuth2 client credentials.

## Development & Testing

```bash
# Setup venv and dependencies
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install pytest pytest-asyncio httpx

# Run tests
uv run pytest
```
