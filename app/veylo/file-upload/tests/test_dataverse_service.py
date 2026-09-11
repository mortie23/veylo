import pytest
from unittest.mock import patch, MagicMock
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


# ======================================================================
# Authorization tests
# ======================================================================

class TestIsUserAuthorizedForSubmission:
    """Tests for is_user_authorized_for_submission with real OData field names."""

    def setup_method(self):
        self.client = DataverseClient(dataverse_url=None)

    def test_admin_role_file_admin(self):
        """File.Admin app role should grant access without any Dataverse calls."""
        claims = {"roles": ["File.Admin"]}
        submission = {"_vey_submittedby_value": "someone-else"}
        assert self.client.is_user_authorized_for_submission(claims, submission) is True

    def test_admin_role_system_administrator(self):
        """SystemAdministrator app role should grant access."""
        claims = {"roles": ["SystemAdministrator"]}
        submission = {"_vey_submittedby_value": "someone-else"}
        assert self.client.is_user_authorized_for_submission(claims, submission) is True

    def test_global_admin_wids(self):
        """Entra ID Global Administrator (via wids claim) should grant access."""
        claims = {"wids": ["62e90394-69f5-4237-9190-012177145e10"]}
        submission = {"_vey_submittedby_value": "someone-else"}
        assert self.client.is_user_authorized_for_submission(claims, submission) is True

    def test_non_admin_wids_denied(self):
        """A non-admin wids role should NOT grant access by itself."""
        claims = {
            "oid": "unknown-oid",
            "wids": ["b79fbf4d-3ef9-4689-8143-76b194e85509"],  # Directory Readers
        }
        submission = {"_vey_submittedby_value": "someone-else"}
        assert self.client.is_user_authorized_for_submission(claims, submission) is False

    @patch.object(DataverseClient, "resolve_contact_id")
    def test_contact_match_via_odata_field(self, mock_resolve):
        """Submitter match using real OData _vey_submittedby_value field."""
        mock_resolve.return_value = "contact-abc-123"

        claims = {"oid": "entra-oid-xyz", "preferred_username": "user@test.com"}
        submission = {"_vey_submittedby_value": "contact-abc-123"}

        assert self.client.is_user_authorized_for_submission(claims, submission) is True
        mock_resolve.assert_called_once_with("entra-oid-xyz", "user@test.com")

    @patch.object(DataverseClient, "resolve_contact_id")
    def test_contact_match_case_insensitive(self, mock_resolve):
        """Contact ID comparison should be case-insensitive."""
        mock_resolve.return_value = "CONTACT-ABC-123"

        claims = {"oid": "oid-1"}
        submission = {"_vey_submittedby_value": "contact-abc-123"}

        assert self.client.is_user_authorized_for_submission(claims, submission) is True

    @patch.object(DataverseClient, "_get_contact_parent_org")
    @patch.object(DataverseClient, "resolve_contact_id")
    def test_org_match_via_parent_account(self, mock_resolve, mock_parent_org):
        """Organization match: caller's parent account matches submission org."""
        mock_resolve.return_value = "contact-different"
        mock_parent_org.return_value = "org-shared-001"

        claims = {"oid": "oid-1"}
        submission = {
            "_vey_submittedby_value": "contact-someone-else",
            "_vey_organization_value": "org-shared-001",
        }

        assert self.client.is_user_authorized_for_submission(claims, submission) is True
        mock_parent_org.assert_called_once_with("contact-different")

    @patch.object(DataverseClient, "_get_contact_parent_org")
    @patch.object(DataverseClient, "resolve_contact_id")
    def test_org_mismatch_denied(self, mock_resolve, mock_parent_org):
        """Different org should be denied."""
        mock_resolve.return_value = "contact-other"
        mock_parent_org.return_value = "org-other"

        claims = {"oid": "oid-1"}
        submission = {
            "_vey_submittedby_value": "contact-someone-else",
            "_vey_organization_value": "org-target",
        }

        assert self.client.is_user_authorized_for_submission(claims, submission) is False

    @patch.object(DataverseClient, "resolve_contact_id")
    def test_unresolvable_identity_denied(self, mock_resolve):
        """If the caller's identity cannot be resolved, deny access."""
        mock_resolve.return_value = None

        claims = {"oid": "unknown-oid"}
        submission = {"_vey_submittedby_value": "contact-abc"}

        assert self.client.is_user_authorized_for_submission(claims, submission) is False

    @patch.object(DataverseClient, "resolve_contact_id")
    def test_local_mock_store_fallback_fields(self, mock_resolve):
        """Authorization should also work with local mock store field names."""
        mock_resolve.return_value = "contact-local"

        claims = {"oid": "local-oid"}
        # Local mock store uses submitted_by_contact_id as fallback
        submission = {"submitted_by_contact_id": "contact-local"}

        assert self.client.is_user_authorized_for_submission(claims, submission) is True


def test_resolve_contact_org_id():
    client = DataverseClient(dataverse_url="https://test.crm.dynamics.com")
    with patch("services.dataverse_service.requests.get") as mock_get, \
         patch.object(DataverseClient, "_get_access_token", return_value="mock-token"):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"_parentcustomerid_value": "acc-999"}
        mock_get.return_value = mock_response

        org_id = client.resolve_contact_org_id("contact-123")
        assert org_id == "acc-999"


def test_create_file_submission_auto_resolves_org():
    client = DataverseClient(dataverse_url="https://test.crm.dynamics.com")
    with patch.object(DataverseClient, "resolve_contact_id", return_value="contact-123"), \
         patch.object(DataverseClient, "resolve_contact_org_id", return_value="auto-org-456"), \
         patch.object(DataverseClient, "_get_access_token", return_value="mock-token"), \
         patch("services.dataverse_service.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.content = b""
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        record = client.create_file_submission(
            submission_id="sub-auto-1",
            filename="data.csv",
            file_size=100,
            file_hash="hash",
            storage_uri="https://blob/data.csv",
            organization_id=None,  # Not provided by client
            submitted_by_contact_id="contact-123"
        )

        sent_payload = mock_post.call_args[1]["json"]
        assert sent_payload["vey_Organization@odata.bind"] == "/accounts(auto-org-456)"
        assert sent_payload["vey_SubmittedBy@odata.bind"] == "/contacts(contact-123)"
        assert record["vey_Organization@odata.bind"] == "/accounts(auto-org-456)"

