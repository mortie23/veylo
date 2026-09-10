import logging
import os
import time
from typing import Any, Dict, Optional, Union
from azure.identity import DefaultAzureCredential
import requests

logger = logging.getLogger(__name__)


class SubmissionStatus:
    UPLOADED = 948740000
    VALIDATING = 948740001
    PROCESSED = 948740002
    PARTIAL_SUCCESS = 948740003
    FAILED = 948740004


STATUS_NAME_TO_CODE = {
    "uploaded": SubmissionStatus.UPLOADED,
    "submitted": SubmissionStatus.UPLOADED,  # Alias
    "validating": SubmissionStatus.VALIDATING,
    "processed": SubmissionStatus.PROCESSED,
    "partial_success": SubmissionStatus.PARTIAL_SUCCESS,
    "partial success": SubmissionStatus.PARTIAL_SUCCESS,
    "failed": SubmissionStatus.FAILED,
}

# In-memory store for local testing when Dataverse URL is not configured
_LOCAL_MOCK_STORE: Dict[str, Dict[str, Any]] = {}


class DataverseClient:
    """Client for interacting with Microsoft Dataverse Web API (vey_FileSubmission entity)."""

    def __init__(self, dataverse_url: Optional[str] = None):
        self.dataverse_url = (dataverse_url or os.environ.get("DATAVERSE_URL", "")).rstrip("/")
        self.credential = DefaultAzureCredential()
        self._token: Optional[str] = None
        self._token_expires_at: float = 0

    def _get_access_token(self) -> str:
        """Acquire Dataverse access token using DefaultAzureCredential with caching."""
        now = time.time()
        if self._token and now < self._token_expires_at:
            return self._token

        if not self.dataverse_url:
            return ""

        token_obj = self.credential.get_token(f"{self.dataverse_url}/.default")
        self._token = token_obj.token
        self._token_expires_at = token_obj.expires_on - 60
        return self._token

    def _headers(self) -> Dict[str, str]:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "Prefer": "return=representation"
        }

    def resolve_contact_id(
        self,
        identifier: Optional[str] = None,
        email: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve a Dataverse contactid from a contact GUID, an Entra ID OID (via adx_externalidentities),
        or the user's email address.
        """
        if not self.dataverse_url or (not identifier and not email):
            return identifier

        headers = self._headers()

        # 1. Check if identifier is already a valid contact ID
        if identifier:
            try:
                endpoint = f"{self.dataverse_url}/api/data/v9.2/contacts({identifier})?$select=contactid"
                res = requests.get(endpoint, headers=headers, timeout=10)
                if res.ok:
                    return res.json().get("contactid")
            except Exception as ex:
                logger.debug(f"Direct contact lookup failed: {ex}")

            # 2. Check adx_externalidentities (links Entra ID OID to Contact)
            try:
                endpoint = (
                    f"{self.dataverse_url}/api/data/v9.2/adx_externalidentities"
                    f"?$filter=adx_username eq '{identifier}'&$select=_adx_contactid_value&$top=1"
                )
                res = requests.get(endpoint, headers=headers, timeout=10)
                if res.ok:
                    items = res.json().get("value", [])
                    if items and items[0].get("_adx_contactid_value"):
                        return items[0]["_adx_contactid_value"]
            except Exception as ex:
                logger.debug(f"External identity lookup failed: {ex}")

        # 3. Fallback: Lookup by email address
        if email:
            try:
                endpoint = (
                    f"{self.dataverse_url}/api/data/v9.2/contacts"
                    f"?$filter=emailaddress1 eq '{email}'&$select=contactid&$top=1"
                )
                res = requests.get(endpoint, headers=headers, timeout=10)
                if res.ok:
                    items = res.json().get("value", [])
                    if items and items[0].get("contactid"):
                        return items[0]["contactid"]
            except Exception as ex:
                logger.debug(f"Email contact lookup failed: {ex}")

        return None

    def create_file_submission(
        self,
        submission_id: str,
        filename: str,
        file_size: int,
        file_hash: str,
        storage_uri: str,
        organization_id: Optional[str] = None,
        submitted_by_contact_id: Optional[str] = None,
        user_email: Optional[str] = None,
        submission_reference: Optional[str] = None,
        schema_version: Optional[str] = None,
        reporting_period_start: Optional[str] = None,
        reporting_period_end: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a draft vey_FileSubmission record in Dataverse."""
        sub_ref = submission_reference or filename
        record: Dict[str, Any] = {
            "vey_filesubmissionid": submission_id,
            "vey_filename": filename,
            "vey_submissionreference": sub_ref,
            "vey_filesizebytes": file_size,
            "vey_filehash": file_hash,
            "vey_storageuri": storage_uri,
            "vey_submissionstatus": SubmissionStatus.UPLOADED,
            "statuscode": 1
        }

        if schema_version:
            record["vey_schemaversion"] = schema_version
        if reporting_period_start:
            record["vey_reportingperiodstart"] = reporting_period_start
        if reporting_period_end:
            record["vey_reportingperiodend"] = reporting_period_end
        if idempotency_key:
            record["vey_idempotencykey"] = idempotency_key

        # Resolve contact ID (from direct ID, Entra OID, or email)
        resolved_contact_id = self.resolve_contact_id(submitted_by_contact_id, user_email)

        if organization_id:
            record["vey_Organization@odata.bind"] = f"/accounts({organization_id})"
        if resolved_contact_id:
            record["vey_SubmittedBy@odata.bind"] = f"/contacts({resolved_contact_id})"

        # Fallback to local in-memory store for local testing
        if not self.dataverse_url:
            logger.info("DATAVERSE_URL not set; storing file submission locally in mock store.")
            _LOCAL_MOCK_STORE[submission_id] = record
            return record

        endpoint = f"{self.dataverse_url}/api/data/v9.2/vey_filesubmissions"
        response = requests.post(endpoint, headers=self._headers(), json=record, timeout=15)
        
        # If binding failed (e.g. invalid account/contact reference or missing AppendTo permissions), retry without bindings to avoid blocking upload
        if response.status_code in (400, 403, 404) and ("@odata.bind" in str(record)):
            logger.warning(f"Dataverse create returned {response.status_code} ({response.text}); retrying without lookups.")
            record.pop("vey_Organization@odata.bind", None)
            record.pop("vey_SubmittedBy@odata.bind", None)
            response = requests.post(endpoint, headers=self._headers(), json=record, timeout=15)

        if not response.ok:
            error_body = response.text
            logger.error(f"Dataverse create vey_filesubmissions failed ({response.status_code}): {error_body}")
            raise RuntimeError(f"Dataverse API {response.status_code}: {error_body}")

        return response.json() if response.content else record

    def update_submission_status(
        self,
        submission_id: str,
        status: Union[int, str] = SubmissionStatus.UPLOADED
    ) -> bool:
        """Update the status of a vey_FileSubmission record."""
        status_code = status if isinstance(status, int) else STATUS_NAME_TO_CODE.get(str(status).lower(), SubmissionStatus.UPLOADED)

        if not self.dataverse_url:
            if submission_id in _LOCAL_MOCK_STORE:
                _LOCAL_MOCK_STORE[submission_id]["vey_submissionstatus"] = status_code
                return True
            return False

        endpoint = f"{self.dataverse_url}/api/data/v9.2/vey_filesubmissions({submission_id})"
        payload = {"vey_submissionstatus": status_code}
        response = requests.patch(endpoint, headers=self._headers(), json=payload, timeout=15)
        response.raise_for_status()
        return True

    def get_file_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a vey_FileSubmission record by its ID."""
        if not self.dataverse_url:
            return _LOCAL_MOCK_STORE.get(submission_id)

        endpoint = f"{self.dataverse_url}/api/data/v9.2/vey_filesubmissions({submission_id})"
        response = requests.get(endpoint, headers=self._headers(), timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def is_user_authorized_for_submission(
        self,
        user_claims: Dict[str, Any],
        submission: Dict[str, Any]
    ) -> bool:
        """
        Verify whether the authenticated user has permission to access the submission.
        Checks contact ownership or matching organization ID.
        """
        user_contact_id = user_claims.get("contact_id")
        user_org_id = user_claims.get("organization_id")

        submission_submitter = submission.get("vey_submittedbyid") or submission.get("submitted_by_contact_id")
        submission_org = submission.get("vey_organizationid") or submission.get("organization_id")

        if user_contact_id and submission_submitter and user_contact_id == submission_submitter:
            return True

        if user_org_id and submission_org and user_org_id == submission_org:
            return True

        # Check for administrative role claim
        roles = user_claims.get("roles", [])
        if "File.Admin" in roles or "SystemAdministrator" in roles:
            return True

        return False
