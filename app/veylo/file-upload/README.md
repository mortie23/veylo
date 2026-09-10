# Azure Function App — File Upload & Download (`app/veylo/file-upload`)

Serverless Azure Function app (Python v2 programming model) coordinating direct-to-storage uploads and downloads between Power Pages and Azure Blob Storage using Entra ID and Dataverse.

## Endpoints

- `POST /api/upload-request`: Authenticates caller, validates metadata, creates a draft `vey_FileSubmission` record in Dataverse, and returns a short-lived User Delegation write-only SAS.
- `POST /api/upload-complete`: Transitions `vey_FileSubmission` record status to `Submitted`.
- `GET /api/download?submissionId=<id>`: Validates caller authorization and returns a short-lived User Delegation read-only SAS with forced `Content-Disposition: attachment`.

## Local Development & Testing

This project uses [`uv`](https://github.com/astral-sh/uv) for fast, deterministic Python environment management and testing:

1. **Run Unit Tests (Offline)**:
   ```bash
   uv run pytest -v
   ```

2. **Add Dependencies**:
   ```bash
   uv add <package-name>
   uv add --dev <test-tool>
   ```

3. **Export Locked Requirements for Azure Deployment**:
   ```bash
   uv export --no-hashes --no-dev -o requirements.txt
   ```

4. **Deploy to Azure**:
   From the repository root:
   ```bash
   ./deploy-func.sh
   ```

## Cloud Infrastructure

The Terraform configuration to provision this Function App, its Storage Account, App Insights, RBAC, and Entra ID App Registrations is located in:
`infra/az/`
