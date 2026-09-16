import json
import logging
import os
import re
import time
import uuid
import azure.functions as func
import requests

from services.auth_service import validate_jwt_token
from services.dataverse_service import DataverseClient, SubmissionStatus
from services.storage_service import StorageService

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

_CONTRACTS_CACHE = {"data": [], "expires_at": 0}

STORAGE_ACCOUNT_NAME = os.environ.get("STORAGE_ACCOUNT_NAME", "")
CONTAINER_NAME = os.environ.get("BLOB_CONTAINER_NAME", "submissions")
MAX_FILE_SIZE_BYTES = int(os.environ.get("MAX_FILE_SIZE_BYTES", 50 * 1024 * 1024))  # 50 MB default

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".txt",
    ".zip"
}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
    "image/png",
    "image/jpeg",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream"
}

storage_service = StorageService()
dataverse_client = DataverseClient()


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and invalid blob characters."""
    base = os.path.basename(filename.replace("\\", "/"))
    clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', base)
    return clean or "upload.bin"


# ---------------------------------------------------------------------------
# Endpoint 0: Contracts Proxy (Cached GET /contracts from GCP Cloud Run)
# ---------------------------------------------------------------------------
@app.route(route="contracts", methods=["GET"])
def get_contracts(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns active data contracts for Power Pages dropdown.
    Proxies to GCP Cloud Run with X-API-Key header and 5-minute in-memory caching.
    """
    now = time.time()
    if _CONTRACTS_CACHE["data"] and now < _CONTRACTS_CACHE["expires_at"]:
        return func.HttpResponse(
            body=json.dumps(_CONTRACTS_CACHE["data"]),
            mimetype="application/json",
            status_code=200
        )

    cloud_run_url = os.environ.get("VEYLO_VALIDATION_SERVICE_URL", "").rstrip("/")
    api_key = os.environ.get("VEYLO_CLOUD_RUN_API_KEY", "")

    if not cloud_run_url:
        return func.HttpResponse(body="[]", mimetype="application/json", status_code=200)

    try:
        headers = {"X-API-Key": api_key} if api_key else {}
        res = requests.get(f"{cloud_run_url}/contracts", headers=headers, timeout=10)
        res.raise_for_status()
        contracts_data = res.json()

        # Cache valid response for 5 minutes
        _CONTRACTS_CACHE["data"] = contracts_data
        _CONTRACTS_CACHE["expires_at"] = now + 300

        return func.HttpResponse(
            body=json.dumps(contracts_data),
            mimetype="application/json",
            status_code=200
        )
    except Exception as ex:
        logging.exception(f"Failed to fetch contracts from Cloud Run: {ex}")
        return func.HttpResponse(
            body=json.dumps(_CONTRACTS_CACHE["data"] or []),
            mimetype="application/json",
            status_code=200
        )


# ---------------------------------------------------------------------------
# Endpoint 1: Request Upload Ticket (Write SAS + Draft Record)
# ---------------------------------------------------------------------------
@app.route(route="upload-request", methods=["POST"])
def request_upload(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing upload ticket request.")

    # 1. Authenticate Entra ID Bearer Token
    user_claims, auth_error = validate_jwt_token(req.headers.get("Authorization"))
    if not user_claims:
        logging.warning(f"Upload request rejected: {auth_error}")
        return func.HttpResponse(
            body=json.dumps({"error": "Unauthorized"}),
            mimetype="application/json",
            status_code=401
        )

    try:
        data = req.get_json()
        filename = data.get("filename", "").strip()
        file_size = int(data.get("fileSizeBytes", 0))
        mime_type = data.get("mimeType", "").strip()
        file_hash = data.get("fileHash", "").strip()
        organization_id = data.get("organizationId")

        # 2. Validate Filename & File Size
        if not filename:
            return func.HttpResponse(
                body=json.dumps({"error": "Filename is required."}),
                mimetype="application/json",
                status_code=400
            )

        _, ext = os.path.splitext(filename)
        if ext.lower() not in ALLOWED_EXTENSIONS:
            return func.HttpResponse(
                body=json.dumps({"error": f"File extension '{ext}' is not permitted."}),
                mimetype="application/json",
                status_code=400
            )

        if mime_type and mime_type.lower() not in ALLOWED_MIME_TYPES:
            return func.HttpResponse(
                body=json.dumps({"error": f"MIME type '{mime_type}' is not supported."}),
                mimetype="application/json",
                status_code=400
            )

        if file_size <= 0 or file_size > MAX_FILE_SIZE_BYTES:
            max_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
            return func.HttpResponse(
                body=json.dumps({"error": f"File size must be between 1 byte and {max_mb} MB."}),
                mimetype="application/json",
                status_code=400
            )

        safe_filename = sanitize_filename(filename)
        submission_id = str(uuid.uuid4())
        blob_name = f"raw/{submission_id}/{safe_filename}"

        submission_reference = (data.get("submissionReference") or "").strip() or safe_filename
        schema_version = (data.get("schemaVersion") or "").strip() or None
        contract_name = (data.get("contractName") or data.get("contract_name") or "").strip() or None
        contract_version = (data.get("contractVersion") or data.get("contract_version") or "").strip() or None
        reporting_period_start = data.get("reportingPeriodStart") or None
        reporting_period_end = data.get("reportingPeriodEnd") or None
        idempotency_key = (data.get("idempotencyKey") or "").strip() or None

        # 3. Create Draft Record in Dataverse (vey_FileSubmission)
        blob_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
        # Prevent IDOR: use token contact_id if available, fallback to body only if not in token claims
        token_contact_id = user_claims.get("contact_id")
        body_contact_id = data.get("contactId")
        if token_contact_id and body_contact_id and token_contact_id != body_contact_id:
            logging.warning(f"Contact ID mismatch: token {token_contact_id} vs body {body_contact_id}")
            contact_id = token_contact_id
        else:
            contact_id = token_contact_id or body_contact_id
        user_email = user_claims.get("preferred_username") or user_claims.get("email") or user_claims.get("upn")
        dataverse_client.create_file_submission(
            submission_id=submission_id,
            filename=safe_filename,
            file_size=file_size,
            file_hash=file_hash,
            storage_uri=blob_url,
            organization_id=organization_id,
            submitted_by_contact_id=contact_id,
            user_email=user_email,
            submission_reference=submission_reference,
            schema_version=schema_version,
            contract_name=contract_name,
            contract_version=contract_version,
            reporting_period_start=reporting_period_start,
            reporting_period_end=reporting_period_end,
            idempotency_key=idempotency_key
        )

        # 4. Generate User Delegation SAS (Write-only, 15 min TTL)
        upload_url = storage_service.generate_upload_sas(blob_name=blob_name, duration_minutes=15)

        return func.HttpResponse(
            body=json.dumps({
                "submissionId": submission_id,
                "blobName": blob_name,
                "uploadUrl": upload_url,
                "expiresInMinutes": 15
            }),
            mimetype="application/json",
            status_code=200
        )
    except ValueError as ex:
        logging.warning(f"Invalid request payload: {ex}")
        return func.HttpResponse(
            body=json.dumps({"error": "Invalid request body format."}),
            mimetype="application/json",
            status_code=400
        )
    except Exception as ex:
        logging.exception(f"Failed to generate upload ticket: {ex}")
        return func.HttpResponse(
            body=json.dumps({"error": f"Internal server error: {type(ex).__name__}: {str(ex)}"}),
            mimetype="application/json",
            status_code=500
        )


# ---------------------------------------------------------------------------
# Endpoint 2: Complete Upload (Transitions vey_FileSubmission to 'Submitted')
# ---------------------------------------------------------------------------
@app.route(route="upload-complete", methods=["POST"])
def complete_upload(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing upload complete notification.")

    # 1. Authenticate Entra ID Bearer Token
    user_claims, auth_error = validate_jwt_token(req.headers.get("Authorization"))
    if not user_claims:
        logging.warning(f"Complete upload rejected: {auth_error}")
        return func.HttpResponse(
            body=json.dumps({"error": "Unauthorized"}),
            mimetype="application/json",
            status_code=401
        )

    try:
        data = req.get_json()
        submission_id = data.get("submissionId")
        if not submission_id:
            return func.HttpResponse(
                body=json.dumps({"error": "submissionId is required."}),
                mimetype="application/json",
                status_code=400
            )

        # 1. Fetch submission details from Dataverse
        submission = dataverse_client.get_file_submission(submission_id)
        if not submission:
            return func.HttpResponse(
                body=json.dumps({"error": f"Submission '{submission_id}' not found."}),
                mimetype="application/json",
                status_code=404
            )

        filename = submission.get("vey_filename") or submission.get("vey_name") or "file.bin"
        blob_name = f"raw/{submission_id}/{filename}"
        contract_name = submission.get("vey_contractname")
        contract_version = submission.get("vey_contractversion")

        # 2. If a contract is specified, dispatch to GCP Cloud Run
        if contract_name:
            read_sas_url = storage_service.generate_download_sas(
                blob_name=blob_name,
                filename=filename,
                duration_minutes=60
            )

            cloud_run_url = os.environ.get("VEYLO_VALIDATION_SERVICE_URL", "").rstrip("/")
            api_key = os.environ.get("VEYLO_CLOUD_RUN_API_KEY", "")

            if cloud_run_url and api_key:
                mime_type = "text/csv" if filename.lower().endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                payload = {
                    "correlation_id": submission_id,
                    "contract_name": contract_name,
                    "contract_version": contract_version or "v1.0.0",
                    "original_filename": filename,
                    "mime_type": mime_type,
                    "sas_url": read_sas_url,
                    "storage_uri": submission.get("vey_storageuri"),
                    "organization_id": submission.get("_vey_organization_value"),
                    "submitted_by_contact_id": submission.get("_vey_submittedby_value"),
                    "reporting_period_start": submission.get("vey_reportingperiodstart"),
                    "reporting_period_end": submission.get("vey_reportingperiodend")
                }

                headers = {
                    "Content-Type": "application/json",
                    "X-API-Key": api_key
                }

                try:
                    res = requests.post(f"{cloud_run_url}/validate", json=payload, headers=headers, timeout=10)
                    if res.status_code in (200, 202):
                        logging.info(f"GCP Cloud Run validation invoked successfully: {res.status_code}")
                        dataverse_client.update_submission_status(submission_id, status=SubmissionStatus.VALIDATING)
                        return func.HttpResponse(
                            body=json.dumps({"status": "Validating", "submissionId": submission_id}),
                            mimetype="application/json",
                            status_code=200
                        )
                    else:
                        logging.error(f"GCP Cloud Run validation dispatch returned HTTP {res.status_code}: {res.text[:200]}")
                        dataverse_client.update_submission_status(submission_id, status=SubmissionStatus.FAILED)
                        return func.HttpResponse(
                            body=json.dumps({"error": "Validation engine rejected submission.", "status": "Failed", "submissionId": submission_id}),
                            mimetype="application/json",
                            status_code=502
                        )
                except Exception as ex:
                    logging.exception(f"Failed to connect to GCP Cloud Run validation service: {ex}")
                    dataverse_client.update_submission_status(submission_id, status=SubmissionStatus.FAILED)
                    return func.HttpResponse(
                        body=json.dumps({"error": "Failed to connect to validation service.", "status": "Failed", "submissionId": submission_id}),
                        mimetype="application/json",
                        status_code=502
                    )

        # Default: No contract specified, mark as Uploaded
        dataverse_client.update_submission_status(submission_id, status=SubmissionStatus.UPLOADED)
        return func.HttpResponse(
            body=json.dumps({"status": "Uploaded", "submissionId": submission_id}),
            mimetype="application/json",
            status_code=200
        )
    except Exception as ex:
        logging.exception(f"Failed to complete upload: {ex}")
        return func.HttpResponse(
            body=json.dumps({"error": f"Internal server error: {type(ex).__name__}: {str(ex)}"}),
            mimetype="application/json",
            status_code=500
        )


# ---------------------------------------------------------------------------
# Endpoint 3: Secure Download (Generates Read-only SAS for Authorized Users)
# ---------------------------------------------------------------------------
@app.route(route="download", methods=["GET"])
def download_file(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing secure download request.")

    # 1. Authenticate Entra ID Bearer Token
    user_claims, auth_error = validate_jwt_token(req.headers.get("Authorization"))
    if not user_claims:
        logging.warning(f"Download rejected: {auth_error}")
        return func.HttpResponse(
            body=json.dumps({"error": "Unauthorized"}),
            mimetype="application/json",
            status_code=401
        )

    submission_id = req.params.get("submissionId")
    if not submission_id:
        return func.HttpResponse(
            body=json.dumps({"error": "submissionId query parameter is required."}),
            mimetype="application/json",
            status_code=400
        )

    caller_contact_id = req.params.get("contactId")

    try:
        # 2. Verify authorization against Dataverse
        submission = dataverse_client.get_file_submission(submission_id)
        if not submission:
            return func.HttpResponse(
                body=json.dumps({"error": "Submission not found."}),
                mimetype="application/json",
                status_code=404
            )

        if not dataverse_client.is_user_authorized_for_submission(
            user_claims, submission, caller_contact_id=caller_contact_id
        ):
            return func.HttpResponse(
                body=json.dumps({"error": "Forbidden: access to this submission is restricted."}),
                mimetype="application/json",
                status_code=403
            )

        filename = submission.get("vey_filename") or submission.get("vey_name", "download.bin")
        blob_name = f"raw/{submission_id}/{filename}"

        # 3. Generate User Delegation Read SAS (15 min TTL)
        download_url = storage_service.generate_download_sas(
            blob_name=blob_name,
            filename=filename,
            duration_minutes=15
        )

        return func.HttpResponse(
            body=json.dumps({
                "downloadUrl": download_url,
                "filename": filename,
                "expiresInMinutes": 15
            }),
            mimetype="application/json",
            status_code=200
        )
    except Exception as ex:
        logging.exception(f"Failed to generate download URL: {ex}")
        return func.HttpResponse(
            body=json.dumps({"error": "Internal server error."}),
            mimetype="application/json",
            status_code=500
        )
