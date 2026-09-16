import json
import pytest
from unittest.mock import patch, MagicMock
import azure.functions as func

from function_app import request_upload, complete_upload, download_file, get_contracts, _CONTRACTS_CACHE


@pytest.fixture
def mock_valid_auth():
    with patch("function_app.validate_jwt_token") as mock_val:
        mock_val.return_value = (
            {
                "oid": "user-oid-1234",
                "contact_id": "contact-guid-5678",
                "preferred_username": "testuser@example.com"
            },
            None
        )
        yield mock_val


def test_upload_request_unauthorized():
    req = func.HttpRequest(
        method="POST",
        url="/api/upload-request",
        headers={},
        body=b"{}"
    )
    resp = request_upload(req)
    assert resp.status_code == 401
    body = json.loads(resp.get_body())
    assert body["error"] == "Unauthorized"


def test_upload_request_invalid_extension(mock_valid_auth):
    req = func.HttpRequest(
        method="POST",
        url="/api/upload-request",
        headers={"Authorization": "Bearer mock-token"},
        body=json.dumps({
            "filename": "malicious.exe",
            "fileSizeBytes": 1024
        }).encode("utf-8")
    )
    resp = request_upload(req)
    assert resp.status_code == 400
    body = json.loads(resp.get_body())
    assert "not permitted" in body["error"]


def test_upload_request_exceeds_max_size(mock_valid_auth):
    req = func.HttpRequest(
        method="POST",
        url="/api/upload-request",
        headers={"Authorization": "Bearer mock-token"},
        body=json.dumps({
            "filename": "large_file.zip",
            "fileSizeBytes": 60 * 1024 * 1024  # 60 MB > 50 MB limit
        }).encode("utf-8")
    )
    resp = request_upload(req)
    assert resp.status_code == 400
    body = json.loads(resp.get_body())
    assert "File size must be between" in body["error"]


@patch("function_app.storage_service.generate_upload_sas")
def test_upload_request_success(mock_sas, mock_valid_auth):
    mock_sas.return_value = "https://stveyportaldev01.blob.core.windows.net/submissions/raw/sub-id/doc.pdf?sas-token"

    req = func.HttpRequest(
        method="POST",
        url="/api/upload-request",
        headers={"Authorization": "Bearer mock-token"},
        body=json.dumps({
            "filename": "annual_report.pdf",
            "fileSizeBytes": 204800,
            "fileHash": "hash12345",
            "organizationId": "org-guid-001",
            "contactId": "contact-guid-5678",
            "submissionReference": "REP-2026",
            "schemaVersion": "1.0"
        }).encode("utf-8")
    )

    resp = request_upload(req)
    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert "submissionId" in data
    assert "blobName" in data
    assert "raw/" in data["blobName"]
    assert "annual_report.pdf" in data["blobName"]
    assert data["uploadUrl"].startswith("https://")
    assert data["expiresInMinutes"] == 15


def test_upload_complete_unauthorized():
    req = func.HttpRequest(
        method="POST",
        url="/api/upload-complete",
        headers={},
        body=b"{}"
    )
    resp = complete_upload(req)
    assert resp.status_code == 401


def test_upload_complete_missing_id(mock_valid_auth):
    req = func.HttpRequest(
        method="POST",
        url="/api/upload-complete",
        headers={"Authorization": "Bearer mock-token"},
        body=b"{}"
    )
    resp = complete_upload(req)
    assert resp.status_code == 400


@patch("function_app.dataverse_client.get_file_submission")
@patch("function_app.dataverse_client.update_submission_status")
def test_upload_complete_success(mock_update, mock_get_sub, mock_valid_auth):
    mock_update.return_value = True
    mock_get_sub.return_value = {
        "vey_filesubmissionid": "sub-id-1234",
        "vey_filename": "annual_report.pdf",
    }

    req = func.HttpRequest(
        method="POST",
        url="/api/upload-complete",
        headers={"Authorization": "Bearer mock-token"},
        body=json.dumps({"submissionId": "sub-id-1234"}).encode("utf-8")
    )
    resp = complete_upload(req)
    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert data["status"] == "Uploaded"
    assert data["submissionId"] == "sub-id-1234"


@patch("function_app.requests.post")
@patch("function_app.storage_service.generate_download_sas", return_value="https://storage.blob.core.windows.net/sub/file.csv?sas")
@patch("function_app.dataverse_client.get_file_submission")
@patch("function_app.dataverse_client.update_submission_status")
def test_upload_complete_with_contract_dispatches_validation(mock_update, mock_get_sub, mock_sas, mock_post, mock_valid_auth, monkeypatch):
    monkeypatch.setenv("VEYLO_VALIDATION_SERVICE_URL", "https://validation.run.app")
    monkeypatch.setenv("VEYLO_CLOUD_RUN_API_KEY", "test-api-key")

    mock_update.return_value = True
    mock_get_sub.return_value = {
        "vey_filesubmissionid": "sub-val-123",
        "vey_filename": "teams.csv",
        "vey_contractname": "nfl-teams",
        "vey_contractversion": "v1.0.0",
        "vey_storageuri": "https://storage/sub-val-123/teams.csv",
        "_vey_organization_value": "org-1",
        "_vey_submittedby_value": "contact-1",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_post.return_value = mock_resp

    req = func.HttpRequest(
        method="POST",
        url="/api/upload-complete",
        headers={"Authorization": "Bearer mock-token"},
        body=json.dumps({"submissionId": "sub-val-123"}).encode("utf-8")
    )
    resp = complete_upload(req)
    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert data["status"] == "Validating"
    assert data["submissionId"] == "sub-val-123"

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["headers"]["X-API-Key"] == "test-api-key"
    assert call_kwargs["json"]["contract_name"] == "nfl-teams"
    assert call_kwargs["json"]["contract_version"] == "v1.0.0"


@patch("function_app.requests.post")
@patch("function_app.storage_service.generate_download_sas", return_value="https://storage.blob.core.windows.net/sub/file.csv?sas")
@patch("function_app.dataverse_client.get_file_submission")
@patch("function_app.dataverse_client.update_submission_status")
def test_upload_complete_with_contract_validation_rejection(mock_update, mock_get_sub, mock_sas, mock_post, mock_valid_auth, monkeypatch):
    monkeypatch.setenv("VEYLO_VALIDATION_SERVICE_URL", "https://validation.run.app")
    monkeypatch.setenv("VEYLO_CLOUD_RUN_API_KEY", "test-api-key")

    mock_update.return_value = True
    mock_get_sub.return_value = {
        "vey_filesubmissionid": "sub-rej-123",
        "vey_filename": "teams.csv",
        "vey_contractname": "nfl-teams",
        "vey_contractversion": "v1.0.0",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal error in engine"
    mock_post.return_value = mock_resp

    req = func.HttpRequest(
        method="POST",
        url="/api/upload-complete",
        headers={"Authorization": "Bearer mock-token"},
        body=json.dumps({"submissionId": "sub-rej-123"}).encode("utf-8")
    )
    resp = complete_upload(req)
    assert resp.status_code == 502
    data = json.loads(resp.get_body())
    assert data["status"] == "Failed"



def test_download_missing_params(mock_valid_auth):
    req = func.HttpRequest(
        method="GET",
        url="/api/download",
        headers={"Authorization": "Bearer mock-token"},
        params={},
        body=b""
    )
    resp = download_file(req)
    assert resp.status_code == 400


@patch("function_app.storage_service.generate_download_sas", return_value="https://sas.url/download")
@patch("function_app.dataverse_client.is_user_authorized_for_submission", return_value=True)
@patch("function_app.dataverse_client.get_file_submission")
def test_download_success_with_contact_id(mock_get_sub, mock_auth, mock_sas, mock_valid_auth):
    mock_get_sub.return_value = {
        "vey_filesubmissionid": "sub-123",
        "vey_filename": "payroll.csv",
        "_vey_submittedby_value": "contact-mj"
    }

    req = func.HttpRequest(
        method="GET",
        url="/api/download",
        headers={"Authorization": "Bearer mock-token"},
        params={"submissionId": "sub-123", "contactId": "contact-mj"},
        body=b""
    )
    resp = download_file(req)
    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert data["downloadUrl"] == "https://sas.url/download"
    assert data["filename"] == "payroll.csv"
    mock_auth.assert_called_once()
    assert mock_auth.call_args[1]["caller_contact_id"] == "contact-mj"


def test_get_contracts_empty_url(monkeypatch):
    monkeypatch.setenv("VEYLO_VALIDATION_SERVICE_URL", "")
    _CONTRACTS_CACHE["data"] = []
    _CONTRACTS_CACHE["expires_at"] = 0

    req = func.HttpRequest(method="GET", url="/api/contracts", headers={}, body=b"")
    resp = get_contracts(req)
    assert resp.status_code == 200
    assert json.loads(resp.get_body()) == []


@patch("function_app.requests.get")
def test_get_contracts_success(mock_get, monkeypatch):
    monkeypatch.setenv("VEYLO_VALIDATION_SERVICE_URL", "https://validation.run.app")
    monkeypatch.setenv("VEYLO_CLOUD_RUN_API_KEY", "secret-key")
    _CONTRACTS_CACHE["data"] = []
    _CONTRACTS_CACHE["expires_at"] = 0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"contract_name": "nfl-teams", "contract_version": "v1.0.0"}
    ]
    mock_get.return_value = mock_resp

    req = func.HttpRequest(method="GET", url="/api/contracts", headers={}, body=b"")
    resp = get_contracts(req)
    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert len(data) == 1
    assert data[0]["contract_name"] == "nfl-teams"

    # Verify cache is populated
    assert _CONTRACTS_CACHE["data"] == data

    # Subsequent call should use cache without invoking requests.get again
    mock_get.reset_mock()
    resp_cached = get_contracts(req)
    assert resp_cached.status_code == 200
    mock_get.assert_not_called()


@patch("function_app.requests.get")
def test_get_contracts_failure_fallback(mock_get, monkeypatch):
    monkeypatch.setenv("VEYLO_VALIDATION_SERVICE_URL", "https://validation.run.app")
    _CONTRACTS_CACHE["data"] = [{"contract_name": "cached-fallback", "contract_version": "v1.0"}]
    _CONTRACTS_CACHE["expires_at"] = 0  # expired

    mock_get.side_effect = Exception("Connection timeout")

    req = func.HttpRequest(method="GET", url="/api/contracts", headers={}, body=b"")
    resp = get_contracts(req)
    assert resp.status_code == 200
    data = json.loads(resp.get_body())
    assert len(data) == 1
    assert data[0]["contract_name"] == "cached-fallback"


@patch("function_app.storage_service.generate_upload_sas", return_value="https://blob/upload")
@patch("function_app.dataverse_client.create_file_submission")
def test_upload_request_idor_contact_id_prevention(mock_create, mock_sas, mock_valid_auth):
    # mock_valid_auth has contact_id "contact-guid-5678"
    req = func.HttpRequest(
        method="POST",
        url="/api/upload-request",
        headers={"Authorization": "Bearer mock-token"},
        body=json.dumps({
            "filename": "data.csv",
            "fileSizeBytes": 100,
            "contactId": "attacker-injected-guid-9999"
        }).encode("utf-8")
    )
    resp = request_upload(req)
    assert resp.status_code == 200
    # The authenticated user's contact_id must take precedence
    assert mock_create.call_args[1]["submitted_by_contact_id"] == "contact-guid-5678"

