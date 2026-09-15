from unittest.mock import MagicMock, patch
from main import process_validation_task
from models.webhook import WebhookPayload
from services.dataverse_callback import (
    STATUS_FAILED,
    STATUS_PROCESSED,
    STATUS_VALIDATING,
    _LOCAL_MOCK_STORE,
)


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "healthy", "service": "data-validation"}


def test_validate_unauthorized(client):
    payload = {
        "correlationId": "sub-1234",
        "sasUrl": "https://example.com/blob.csv",
        "contractName": "customer-returns",
        "contractVersion": "v2.1.0",
        "originalFilename": "returns.csv",
    }
    # No X-API-Key header
    res = client.post("/validate", json=payload)
    assert res.status_code == 401


def test_validate_accepted(client):
    payload = {
        "correlationId": "sub-1234",
        "sasUrl": "https://example.com/blob.csv",
        "contractName": "customer-returns",
        "contractVersion": "v2.1.0",
        "originalFilename": "returns.csv",
        "mimeType": "text/csv",
        "fileSizeBytes": 1024,
    }
    headers = {"X-API-Key": "test-secret-api-key"}
    res = client.post("/validate", json=payload, headers=headers)
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "Accepted"
    assert data["correlationId"] == "sub-1234"


def test_contracts_unauthorized(client):
    res = client.get("/contracts")
    assert res.status_code == 401

    res = client.post("/contracts", json={"contract_name": "test", "contract_version": "v1.0.0"})
    assert res.status_code == 401


def test_create_and_list_contracts_admin(client):
    new_contract = {
        "contract_name": "vendor-payments",
        "contract_version": "v1.0.0",
        "data_steward_email": "steward@acme.com",
        "entities": [
            {
                "tgt_entity_name": "payments_raw",
                "attributes": [
                    {
                        "src_field_name": "Payment ID",
                        "tgt_field_name": "payment_id",
                        "tgt_data_type": "STRING",
                        "is_pk": True,
                        "is_nullable": False,
                    }
                ]
            }
        ]
    }
    headers = {"X-API-Key": "test-secret-api-key"}

    create_res = client.post("/contracts", json=new_contract, headers=headers)
    assert create_res.status_code == 201
    assert "data_contract_id" in create_res.json()

    list_res = client.get("/contracts", headers=headers)
    assert list_res.status_code == 200
    contracts = list_res.json()
    assert any(c["contract_name"] == "vendor-payments" for c in contracts)


def test_process_validation_task_end_to_end_success(sample_customer_returns_contract, db_session):
    submission_id = "sub-e2e-success"
    csv_content = (
        b"Return ID,Return Date,Country,Email,Amount\n"
        b"101,2026-09-11,AUS,user@test.com,150.00\n"
    )

    payload = WebhookPayload(
        correlation_id=submission_id,
        sas_url="https://example.com/blob.csv",
        contract_name="customer-returns",
        contract_version="v2.1.0",
        original_filename="returns.csv",
    )

    with patch("services.file_parser.FileParser.stream_file_from_sas", return_value=csv_content), \
         patch("main.SessionLocal", return_value=db_session), \
         patch("services.bigquery_loader.BigQueryLoader.ensure_target_table"), \
         patch("services.bigquery_loader.BigQueryLoader.load_dataframe"):

        process_validation_task(payload)

    assert _LOCAL_MOCK_STORE[submission_id]["vey_submissionstatus"] == STATUS_PROCESSED


def test_process_validation_task_end_to_end_failure(sample_customer_returns_contract, db_session):
    submission_id = "sub-e2e-failure"
    # Row 1 has invalid date
    csv_content = (
        b"Return ID,Return Date,Country,Email,Amount\n"
        b"101,31/13/2026,AUS,user@test.com,150.00\n"
    )

    payload = WebhookPayload(
        correlation_id=submission_id,
        sas_url="https://example.com/blob.csv",
        contract_name="customer-returns",
        contract_version="v2.1.0",
        original_filename="returns.csv",
    )

    with patch("services.file_parser.FileParser.stream_file_from_sas", return_value=csv_content), \
         patch("main.SessionLocal", return_value=db_session):

        process_validation_task(payload)

    assert _LOCAL_MOCK_STORE[submission_id]["vey_submissionstatus"] == STATUS_FAILED
    assert len(_LOCAL_MOCK_STORE[submission_id]["errors"]) == 1
    assert _LOCAL_MOCK_STORE[submission_id]["errors"][0]["error_code"] == "TYPE_CAST_FAILED"
