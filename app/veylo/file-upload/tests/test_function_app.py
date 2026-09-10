import json
import pytest
from unittest.mock import patch, MagicMock
import azure.functions as func

from function_app import request_upload, complete_upload, download_file


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


@patch("function_app.dataverse_client.update_submission_status")
def test_upload_complete_success(mock_update, mock_valid_auth):
    mock_update.return_value = True

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
