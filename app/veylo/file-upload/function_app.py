import json
import logging
import os
import re
import uuid
import azure.functions as func

from services.auth_service import validate_jwt_token
from services.dataverse_service import DataverseClient
from services.storage_service import StorageService

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

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
# Endpoint 1: Request Upload Ticket (Write SAS + Draft Record)
# ---------------------------------------------------------------------------
@app.route(route="upload-request", methods=["POST"])
def request_upload(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing upload ticket request.")

    # 1. Authenticate Entra ID Bearer Token
    user_claims = validate_jwt_token(req.headers.get("Authorization"))
    if not user_claims:
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

        # 3. Create Draft Record in Dataverse (vey_FileSubmission)
        blob_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
        dataverse_client.create_file_submission(
            submission_id=submission_id,
            filename=safe_filename,
            file_size=file_size,
            file_hash=file_hash,
            storage_uri=blob_url,
            organization_id=organization_id,
            submitted_by_contact_id=user_claims.get("contact_id")
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
            body=json.dumps({"error": "Internal server error."}),
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
    user_claims = validate_jwt_token(req.headers.get("Authorization"))
    if not user_claims:
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

        # 2. Mark Dataverse record as Submitted
        success = dataverse_client.update_submission_status(submission_id, status="Submitted")
        if not success:
            return func.HttpResponse(
                body=json.dumps({"error": f"Submission '{submission_id}' not found."}),
                mimetype="application/json",
                status_code=404
            )

        return func.HttpResponse(
            body=json.dumps({"status": "Submitted", "submissionId": submission_id}),
            mimetype="application/json",
            status_code=200
        )
    except Exception as ex:
        logging.exception(f"Failed to complete upload: {ex}")
        return func.HttpResponse(
            body=json.dumps({"error": "Internal server error."}),
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
    user_claims = validate_jwt_token(req.headers.get("Authorization"))
    if not user_claims:
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

    try:
        # 2. Verify authorization against Dataverse
        submission = dataverse_client.get_file_submission(submission_id)
        if not submission:
            return func.HttpResponse(
                body=json.dumps({"error": "Submission not found."}),
                mimetype="application/json",
                status_code=404
            )

        if not dataverse_client.is_user_authorized_for_submission(user_claims, submission):
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
