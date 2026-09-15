from unittest.mock import MagicMock
import pandas as pd
from services.bigquery_loader import BigQueryLoader, sanitize_table_name
from models.orm import Attribute


def test_sanitize_table_name():
    assert sanitize_table_name("customer-returns") == "customer_returns"
    assert sanitize_table_name("Returns Detail 2026!") == "returns_detail_2026"


def test_get_table_name():
    loader = BigQueryLoader(project_id="test-proj")
    name = loader.get_table_name("customer-returns", "returns-detail")
    assert name == "customer_returns__returns_detail"


def test_ensure_target_table_calls_create():
    mock_client = MagicMock()
    loader = BigQueryLoader(client=mock_client, project_id="test-proj")

    attrs = [
        Attribute(tgt_field_name="id", tgt_data_type="INT64", is_nullable=False),
        Attribute(tgt_field_name="name", tgt_data_type="STRING", is_nullable=True),
    ]

    loader.ensure_target_table("veylo_bronze", "customer_returns__detail", attrs)

    assert mock_client.create_table.called
    table_arg = mock_client.create_table.call_args[0][0]
    assert table_arg.table_id == "customer_returns__detail"
    assert table_arg.dataset_id == "veylo_bronze"
    assert table_arg.project == "test-proj"

    # Verify metadata columns exist in schema
    schema_names = [f.name for f in table_arg.schema]
    assert "id" in schema_names
    assert "name" in schema_names
    assert "_veylo_submission_id" in schema_names
    assert "_veylo_loaded_at" in schema_names


def test_load_dataframe_executes_load_job():
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_client.load_table_from_dataframe.return_value = mock_job

    loader = BigQueryLoader(client=mock_client, project_id="test-proj")

    df = pd.DataFrame([{"id": 1, "name": "item"}])
    attrs = [
        Attribute(tgt_field_name="id", tgt_data_type="INT64", is_nullable=False),
        Attribute(tgt_field_name="name", tgt_data_type="STRING", is_nullable=True),
    ]

    loader.load_dataframe(
        df=df,
        dataset_name="veylo_bronze",
        table_name="customer_returns__detail",
        submission_id="sub-1234",
        attributes=attrs,
    )

    assert mock_client.load_table_from_dataframe.called
    called_df = mock_client.load_table_from_dataframe.call_args[0][0]
    assert "_veylo_submission_id" in called_df.columns
    assert "_veylo_loaded_at" in called_df.columns
    assert called_df.iloc[0]["_veylo_submission_id"] == "sub-1234"
    assert mock_job.result.called
