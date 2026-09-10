import os
import pytest

# Ensure tests run with clean environment defaults
@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", "d63e78bd-9ee3-4a7d-a868-738824c13bd1")
    monkeypatch.setenv("API_AUDIENCE", "api://func-vey-portal-dev")
    monkeypatch.setenv("STORAGE_ACCOUNT_NAME", "stveyportaldev01")
    monkeypatch.setenv("BLOB_CONTAINER_NAME", "submissions")
    monkeypatch.setenv("DATAVERSE_URL", "")  # Use in-memory mock store by default in unit tests
