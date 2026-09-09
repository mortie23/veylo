# Azure Function App — File Upload & Download (`app/veylo/file-upload`)

Serverless Azure Function app (Python v2 programming model) coordinating direct-to-storage uploads and downloads between Power Pages and Azure Blob Storage using Entra ID and Dataverse.

## Endpoints

- `POST /api/upload-request`: Authenticates caller, validates metadata, creates a draft `vey_FileSubmission` record in Dataverse, and returns a short-lived User Delegation write-only SAS.
- `POST /api/upload-complete`: Transitions `vey_FileSubmission` record status to `Submitted`.
- `GET /api/download?submissionId=<id>`: Validates caller authorization and returns a short-lived User Delegation read-only SAS with forced `Content-Disposition: attachment`.

## Local Development & Testing

1. Create and activate a Python 3.11 virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure local settings:
   ```bash
   cp local.settings.json.example local.settings.json
   ```

3. Run Azure Functions Core Tools:
   ```bash
   func start
   ```

## Cloud Infrastructure

The Terraform configuration to provision this Function App, its Storage Account, App Insights, RBAC, and Entra ID App Registrations is located in:
`infra/az/`
