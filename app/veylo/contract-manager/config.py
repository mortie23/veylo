import os
from functools import lru_cache
from typing import Optional
import google.auth
from google.auth.exceptions import DefaultCredentialsError


class Settings:
    def __init__(self):
        self.env = os.environ.get("ENV", "dev")
        self.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod-veylo")
        self.port = int(os.environ.get("PORT", 8080))
        self.debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")

        # GCP & BigQuery Config
        self.gcp_project_id = os.environ.get("GCP_PROJECT_ID", os.environ.get("GOOGLE_CLOUD_PROJECT", "veylo-gcp-dev"))
        self.bq_config_dataset = os.environ.get("BQ_CONFIG_DATASET", "veylo_config")
        self.bq_bronze_dataset = os.environ.get("BQ_BRONZE_DATASET", "veylo_bronze")

        # Storage backend preference: "sqlite" (default for local dev), "bigquery", or "auto"
        self.data_backend = os.environ.get("DATA_BACKEND", "sqlite").lower()

        # Explicit database URL override
        self.database_url_override = os.environ.get("DATABASE_URL")

        # Entra ID Authentication Config
        self.entra_tenant_id = os.environ.get("ENTRA_TENANT_ID", "")
        self.entra_client_id = os.environ.get("ENTRA_CLIENT_ID", "")
        self.entra_client_secret = os.environ.get("ENTRA_CLIENT_SECRET", "")
        self.entra_redirect_uri = os.environ.get("ENTRA_REDIRECT_URI", "")

    @property
    def is_auth_enabled(self) -> bool:
        """Determines if Entra ID authentication is enforced."""
        env_override = os.environ.get("AUTH_ENABLED")
        if env_override is not None:
            return env_override.lower() in ("1", "true", "yes")
        return bool(self.entra_client_secret and self.entra_client_id)

    @property
    def entra_authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}"


    @property
    def effective_database_url(self) -> str:
        """
        Determines the SQLAlchemy database URL.
        1. If DATABASE_URL is set, use it.
        2. If DATA_BACKEND is 'sqlite', use local SQLite.
        3. If DATA_BACKEND is 'bigquery', use BigQuery.
        4. If DATA_BACKEND is 'auto', test for Google ADC credentials:
           - If ADC credentials work, connect to BigQuery.
           - Otherwise, gracefully fall back to local SQLite.
        """
        if self.database_url_override:
            return self.database_url_override

        if self.data_backend == "sqlite":
            return "sqlite:///veylo_contracts.db"

        if self.data_backend == "bigquery":
            return f"bigquery://{self.gcp_project_id}/{self.bq_config_dataset}"

        # "auto" mode: check if ADC credentials are present
        try:
            google.auth.default()
            return f"bigquery://{self.gcp_project_id}/{self.bq_config_dataset}"
        except (DefaultCredentialsError, Exception):
            return "sqlite:///veylo_contracts.db"

    @property
    def is_sqlite(self) -> bool:
        return self.effective_database_url.startswith("sqlite")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
