import logging
import os
import time
from typing import Any, Dict, Optional
from azure.identity import DefaultAzureCredential
import requests

logger = logging.getLogger(__name__)

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

    def create_file_submission(
        self,
        submission_id: str,
        filename: str,
        file_size: int,
        file_hash: str,
        storage_uri: str,
        organization_id: Optional[str] = None,
        submitted_by_contact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a draft vey_FileSubmission record in Dataverse."""
        record = {
            "vey_filesubmissionid": submission_id,
            "vey_name": filename,
            "vey_filename": filename,
            "vey_filesizebytes": file_size,
            "vey_filehash": file_hash,
            "vey_storageuri": storage_uri,
            "vey_submissionstatus": "Draft",
            "statuscode": 1
        }

        if organization_id:
            record["vey_organizationid"] = organization_id
        if submitted_by_contact_id:
            record["vey_submittedbyid"] = submitted_by_contact_id

        # Fallback to local in-memory store for local testing
        if not self.dataverse_url:
            logger.info("DATAVERSE_URL not set; storing file submission locally in mock store.")
            _LOCAL_MOCK_STORE[submission_id] = record
            return record

        endpoint = f"{self.dataverse_url}/api/data/v9.2/vey_filesubmissions"
        response = requests.post(endpoint, headers=self._headers(), json=record, timeout=15)
        response.raise_for_status()
        return response.json() if response.content else record

    def update_submission_status(self, submission_id: str, status: str = "Submitted") -> bool:
        """Update the status of a vey_FileSubmission record."""
        if not self.dataverse_url:
            if submission_id in _LOCAL_MOCK_STORE:
                _LOCAL_MOCK_STORE[submission_id]["vey_submissionstatus"] = status
                return True
            return False

        endpoint = f"{self.dataverse_url}/api/data/v9.2/vey_filesubmissions({submission_id})"
        payload = {"vey_submissionstatus": status}
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
