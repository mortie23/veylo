import logging
import time
import uuid
from typing import Any, Dict, List, Optional
import msal
import requests

from config import get_settings
from models.validation_result import ValidationErrorDetail

logger = logging.getLogger(__name__)

# Submission Status Codes matching Dataverse Choice
STATUS_VALIDATING = 948740001
STATUS_PROCESSED = 948740002
STATUS_FAILED = 948740004

# In-memory store for local testing when Dataverse URL is not configured
_LOCAL_MOCK_STORE: Dict[str, Dict[str, Any]] = {}


class DataverseCallbackError(Exception):
    """Raised when Dataverse callback fails."""
    pass


class DataverseCallback:
    """Service to push validation results and error logs back to Microsoft Dataverse via OData Web API."""

    def __init__(
        self,
        dataverse_url: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        settings = get_settings()
        if dataverse_url is not None:
            self.dataverse_url = dataverse_url.rstrip("/")
        else:
            self.dataverse_url = (settings.dataverse_url or "").rstrip("/")
        self.client_id = client_id or settings.dataverse_client_id or ""
        self.client_secret = client_secret or settings.dataverse_client_secret or ""
        self.tenant_id = tenant_id or settings.dataverse_tenant_id or ""

        self._msal_app: Optional[msal.ConfidentialClientApplication] = None
        self._token: Optional[str] = None
        self._token_expires_at: float = 0

    @property
    def is_configured(self) -> bool:
        """Returns True if Dataverse URL and all required Entra ID credentials are provided."""
        return bool(self.dataverse_url and self.client_id and self.client_secret and self.tenant_id)

    def _get_access_token(self) -> str:
        """Acquires OAuth2 token using MSAL client credentials with in-memory caching."""
        now = time.time()
        if self._token and now < self._token_expires_at:
            return self._token

        if not (self.dataverse_url and self.client_id and self.client_secret and self.tenant_id):
            logger.debug("Dataverse credentials not fully set; running in local/mock mode.")
            return ""

        if self._msal_app is None:
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            self._msal_app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=authority,
            )

        scopes = [f"{self.dataverse_url}/.default"]
        result = self._msal_app.acquire_token_for_client(scopes=scopes)

        if "access_token" in result:
            self._token = result["access_token"]
            expires_in = result.get("expires_in", 3600)
            self._token_expires_at = now + expires_in - 60
            return self._token
        else:
            error_desc = result.get("error_description", result.get("error"))
            raise DataverseCallbackError(f"Failed to acquire Dataverse access token from Entra ID: {error_desc}")

    def _headers(self) -> Dict[str, str]:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "Prefer": "return=representation",
        }

    def update_submission_status(
        self,
        submission_id: str,
        status: int,
        summary: Optional[str] = None
    ) -> bool:
        """Updates submission status and summary on vey_FileSubmission."""
        payload: Dict[str, Any] = {
            "vey_submissionstatus": status,
        }

        if not self.is_configured:
            logger.info(f"[Local Mock] Updating vey_FileSubmission {submission_id}: {payload}")
            if submission_id not in _LOCAL_MOCK_STORE:
                _LOCAL_MOCK_STORE[submission_id] = {"id": submission_id, "errors": []}
            _LOCAL_MOCK_STORE[submission_id].update(payload)
            return True

        endpoint = f"{self.dataverse_url}/api/data/v9.2/vey_filesubmissions({submission_id})"
        try:
            res = requests.patch(endpoint, headers=self._headers(), json=payload, timeout=15)
            res.raise_for_status()
            logger.info(f"Updated Dataverse submission {submission_id} to status {status}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to update Dataverse submission status for {submission_id}: {e}")
            raise DataverseCallbackError(f"Dataverse update submission failed: {e}") from e

    def report_errors(
        self,
        submission_id: str,
        errors: List[ValidationErrorDetail]
    ) -> int:
        """
        Pushes row-level errors to Dataverse vey_FileIngestionError entity.
        Attempts OData $batch insertion first; falls back to individual requests if $batch fails.
        """
        if not errors:
            return 0

        if not self.is_configured:
            logger.info(f"[Local Mock] Reporting {len(errors)} errors for submission {submission_id}")
            if submission_id not in _LOCAL_MOCK_STORE:
                _LOCAL_MOCK_STORE[submission_id] = {"id": submission_id, "errors": []}
            _LOCAL_MOCK_STORE[submission_id].setdefault("errors", []).extend([e.model_dump() for e in errors])
            return len(errors)

        # First attempt: batch insert
        try:
            return self._batch_insert_errors(submission_id, errors)
        except Exception as e:
            logger.warning(f"OData $batch error insert failed ({e}); falling back to individual inserts.")
            return self._individual_insert_errors(submission_id, errors)

    def _batch_insert_errors(
        self,
        submission_id: str,
        errors: List[ValidationErrorDetail],
        batch_size: int = 100
    ) -> int:
        """Splits errors into OData $batch changesets and posts them to Dataverse."""
        token = self._get_access_token()
        endpoint = f"{self.dataverse_url}/api/data/v9.2/$batch"
        total_inserted = 0

        for i in range(0, len(errors), batch_size):
            chunk = errors[i : i + batch_size]
            batch_boundary = f"batch_{uuid.uuid4()}"
            changeset_boundary = f"changeset_{uuid.uuid4()}"

            body_lines = [
                f"--{batch_boundary}",
                f"Content-Type: multipart/mixed; boundary={changeset_boundary}",
                "",
            ]

            for idx, err in enumerate(chunk):
                record = {
                    "vey_FileSubmission@odata.bind": f"/vey_filesubmissions({submission_id})",
                    "vey_errorcode": err.error_code,
                    "vey_errormessage": err.error_message[:2000],
                    "vey_errorreference": (err.column_name or "")[:200],
                    "vey_rawpayload": (err.raw_value or "")[:4000],
                }
                if err.row_number is not None:
                    record["vey_rownumber"] = err.row_number

                import json
                body_lines.extend([
                    f"--{changeset_boundary}",
                    "Content-Type: application/http",
                    "Content-Transfer-Encoding: binary",
                    f"Content-ID: {idx + 1}",
                    "",
                    "POST /api/data/v9.2/vey_fileingestionerrors HTTP/1.1",
                    "Content-Type: application/json; type=entry",
                    "",
                    json.dumps(record),
                    "",
                ])

            body_lines.extend([
                f"--{changeset_boundary}--",
                f"--{batch_boundary}--",
                "",
            ])

            batch_payload = "\r\n".join(body_lines).encode("utf-8")
            headers = {
                "Authorization": f"Bearer {token}",
                "OData-MaxVersion": "4.0",
                "OData-Version": "4.0",
                "Content-Type": f"multipart/mixed; boundary={batch_boundary}",
                "Accept": "application/json",
            }

            res = requests.post(endpoint, headers=headers, data=batch_payload, timeout=30)
            res.raise_for_status()
            total_inserted += len(chunk)

        return total_inserted

    def _individual_insert_errors(
        self,
        submission_id: str,
        errors: List[ValidationErrorDetail]
    ) -> int:
        """Fallback individual insert of errors."""
        endpoint = f"{self.dataverse_url}/api/data/v9.2/vey_fileingestionerrors"
        headers = self._headers()
        count = 0

        for err in errors:
            record = {
                "vey_FileSubmission@odata.bind": f"/vey_filesubmissions({submission_id})",
                "vey_errorcode": err.error_code,
                "vey_errormessage": err.error_message[:2000],
                "vey_errorreference": (err.column_name or "")[:200],
                "vey_rawpayload": (err.raw_value or "")[:4000],
            }
            if err.row_number is not None:
                record["vey_rownumber"] = err.row_number

            try:
                res = requests.post(endpoint, headers=headers, json=record, timeout=10)
                if res.status_code in (200, 201, 204):
                    count += 1
            except Exception as e:
                logger.debug(f"Individual error record insertion failed: {e}")

        return count
