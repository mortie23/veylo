from datetime import datetime, timezone
import logging
import re
from typing import List, Optional
import pandas as pd
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from config import get_settings
from models.orm import Attribute, Entity

logger = logging.getLogger(__name__)


def sanitize_table_name(name: str) -> str:
    """Sanitizes names for BigQuery table naming conventions."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_").lower()


class BigQueryLoader:
    """Service to auto-create bronze tables and load validated DataFrames into BigQuery."""

    def __init__(self, client: Optional[bigquery.Client] = None, project_id: Optional[str] = None):
        self.settings = get_settings()
        self.project_id = project_id or self.settings.gcp_project_id
        self._client = client

    @property
    def client(self) -> bigquery.Client:
        if self._client is None:
            self._client = bigquery.Client(project=self.project_id)
        return self._client

    def get_table_name(self, contract_name: str, entity_name: str) -> str:
        """Returns standard table name pattern: <contract_name>__<entity_name>."""
        c_name = sanitize_table_name(contract_name)
        e_name = sanitize_table_name(entity_name)
        return f"{c_name}__{e_name}"

    def ensure_target_table(
        self,
        dataset_name: str,
        table_name: str,
        attributes: List[Attribute]
    ) -> bigquery.Table:
        """
        Auto-creates the BigQuery target table in the bronze dataset if it does not exist.
        Appends the required metadata columns (_veylo_submission_id and _veylo_loaded_at).
        """
        table_id = f"{self.project_id}.{dataset_name}.{table_name}"

        schema = []
        for attr in attributes:
            bq_type = self._map_to_bq_type(attr.tgt_data_type)
            mode = "NULLABLE" if attr.is_nullable else "REQUIRED"
            schema.append(bigquery.SchemaField(attr.tgt_field_name, bq_type, mode=mode))

        # Metadata columns required by Veylo bronze architecture
        schema.append(bigquery.SchemaField("_veylo_submission_id", "STRING", mode="REQUIRED"))
        schema.append(bigquery.SchemaField("_veylo_loaded_at", "TIMESTAMP", mode="REQUIRED"))

        table = bigquery.Table(table_id, schema=schema)
        try:
            created_table = self.client.create_table(table, exists_ok=True)
            logger.info(f"Target table ready: {table_id}")
            return created_table
        except Exception as e:
            logger.error(f"Failed to ensure BigQuery table {table_id}: {e}")
            raise

    def load_dataframe(
        self,
        df: pd.DataFrame,
        dataset_name: str,
        table_name: str,
        submission_id: str,
        attributes: List[Attribute],
    ) -> bigquery.LoadJob:
        """
        Loads a validated DataFrame into BigQuery bronze table using WRITE_TRUNCATE.
        Auto-creates the table if not present, and injects metadata columns.
        """
        table_id = f"{self.project_id}.{dataset_name}.{table_name}"

        # Ensure table exists before loading
        self.ensure_target_table(dataset_name, table_name, attributes)

        # Append bronze metadata columns
        load_df = df.copy()
        load_df["_veylo_submission_id"] = submission_id
        load_df["_veylo_loaded_at"] = datetime.now(timezone.utc)

        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )

        logger.info(f"Starting BigQuery load job into {table_id} (WRITE_TRUNCATE, {len(load_df)} rows)")
        load_job = self.client.load_table_from_dataframe(
            load_df,
            table_id,
            job_config=job_config,
        )
        load_job.result()  # Wait for the job to complete
        logger.info(f"Successfully loaded {len(load_df)} rows into {table_id}")
        return load_job

    @staticmethod
    def _map_to_bq_type(data_type: str) -> str:
        t = data_type.upper().strip()
        mapping = {
            "STRING": "STRING",
            "TEXT": "STRING",
            "INT64": "INT64",
            "INTEGER": "INT64",
            "INT": "INT64",
            "FLOAT64": "FLOAT64",
            "FLOAT": "FLOAT64",
            "NUMERIC": "NUMERIC",
            "DECIMAL": "NUMERIC",
            "BOOL": "BOOL",
            "BOOLEAN": "BOOL",
            "DATE": "DATE",
            "TIMESTAMP": "TIMESTAMP",
            "DATETIME": "DATETIME",
        }
        return mapping.get(t, "STRING")
