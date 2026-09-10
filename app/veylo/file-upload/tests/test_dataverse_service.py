import pytest
from services.dataverse_service import (
    DataverseClient,
    SubmissionStatus,
    STATUS_NAME_TO_CODE,
    _LOCAL_MOCK_STORE
)


def test_submission_status_constants():
    assert SubmissionStatus.UPLOADED == 948740000
    assert SubmissionStatus.VALIDATING == 948740001
    assert SubmissionStatus.PROCESSED == 948740002
    assert SubmissionStatus.PARTIAL_SUCCESS == 948740003
    assert SubmissionStatus.FAILED == 948740004
    assert STATUS_NAME_TO_CODE["submitted"] == SubmissionStatus.UPLOADED
    assert STATUS_NAME_TO_CODE["uploaded"] == SubmissionStatus.UPLOADED


def test_create_file_submission_local_store():
    client = DataverseClient(dataverse_url=None)
    sub_id = "test-sub-1234"

    record = client.create_file_submission(
        submission_id=sub_id,
        filename="payroll_2026_q1.csv",
        file_size=10240,
        file_hash="abc123hash",
        storage_uri="https://stveyportaldev01.blob.core.windows.net/submissions/raw/1234/payroll.csv",
        organization_id="org-guid-001",
        submitted_by_contact_id="contact-guid-002",
        submission_reference="REF-2026-001",
        schema_version="v2.1"
    )

    assert record["vey_filesubmissionid"] == sub_id
    assert record["vey_filename"] == "payroll_2026_q1.csv"
    assert record["vey_submissionreference"] == "REF-2026-001"
    assert record["vey_filesizebytes"] == 10240
    assert record["vey_filehash"] == "abc123hash"
    assert record["vey_submissionstatus"] == SubmissionStatus.UPLOADED
    assert record["vey_schemaversion"] == "v2.1"
    assert record["statuscode"] == 1

    # CRITICAL: vey_name must NOT exist on vey_filesubmission
    assert "vey_name" not in record

    # CRITICAL: Read-only _value fields must NOT exist in the payload
    assert "_vey_organization_value" not in record
    assert "_vey_submittedby_value" not in record

    # Lookup navigation binds
    assert record["vey_Organization@odata.bind"] == "/accounts(org-guid-001)"
    assert record["vey_SubmittedBy@odata.bind"] == "/contacts(contact-guid-002)"

    # Verify stored in mock store
    assert sub_id in _LOCAL_MOCK_STORE


def test_update_submission_status_local_store():
    client = DataverseClient(dataverse_url=None)
    sub_id = "test-sub-update-5678"

    client.create_file_submission(
        submission_id=sub_id,
        filename="test.pdf",
        file_size=500,
        file_hash="hash5678",
        storage_uri="https://example.com/test.pdf"
    )

    # Update with integer constant
    success = client.update_submission_status(sub_id, SubmissionStatus.PROCESSED)
    assert success is True
    assert _LOCAL_MOCK_STORE[sub_id]["vey_submissionstatus"] == 948740002

    # Update with string name alias
    success = client.update_submission_status(sub_id, "failed")
    assert success is True
    assert _LOCAL_MOCK_STORE[sub_id]["vey_submissionstatus"] == 948740004
