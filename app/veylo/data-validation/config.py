import os
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Cloud Platform & BigQuery
    gcp_project_id: str = os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT_ID", "veylo-gcp-dev"))
    bq_config_dataset: str = "veylo_config"
    bq_bronze_dataset: str = "veylo_bronze"

    # Database URL override (e.g. for testing with sqlite:/// or postgresql)
    database_url: Optional[str] = None

    # Inbound Webhook Authentication
    api_key: str = os.environ.get("VEYLO_CLOUD_RUN_API_KEY", os.environ.get("API_KEY", ""))

    # Microsoft Dataverse & Entra ID Callback
    dataverse_url: Optional[str] = os.environ.get("DATAVERSE_URL")
    dataverse_client_id: Optional[str] = os.environ.get("VEYLO_DATAVERSE_CLIENT_ID", os.environ.get("DATAVERSE_CLIENT_ID"))
    dataverse_client_secret: Optional[str] = os.environ.get("VEYLO_DATAVERSE_CLIENT_SECRET", os.environ.get("DATAVERSE_CLIENT_SECRET"))
    dataverse_tenant_id: Optional[str] = os.environ.get("VEYLO_DATAVERSE_TENANT_ID", os.environ.get("DATAVERSE_TENANT_ID"))

    # Runtime Settings
    port: int = int(os.environ.get("PORT", 8080))
    log_level: str = "INFO"

    @property
    def effective_database_url(self) -> str:
        """Returns explicitly set database_url, or constructs the BigQuery SQLAlchemy URL."""
        if self.database_url:
            return self.database_url
        return f"bigquery://{self.gcp_project_id}/{self.bq_config_dataset}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
