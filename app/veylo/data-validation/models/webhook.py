from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, AliasChoices


class WebhookPayload(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow"
    )

    correlation_id: str = Field(
        ...,
        validation_alias=AliasChoices("correlationId", "submissionId", "correlation_id", "submission_id"),
        description="Correlation ID mapping to Dataverse vey_FileSubmission record"
    )
    sas_url: str = Field(
        ...,
        validation_alias=AliasChoices("sasUrl", "sas_url"),
        description="Ephemeral read-only SAS URL for streaming the file from Azure Blob Storage"
    )
    contract_name: str = Field(
        ...,
        validation_alias=AliasChoices("contractName", "contract_name"),
        description="Data contract identifier (e.g. 'customer-returns')"
    )
    contract_version: str = Field(
        ...,
        validation_alias=AliasChoices("contractVersion", "contract_version"),
        description="Data contract semantic version (e.g. 'v2.1.0')"
    )
    original_filename: str = Field(
        ...,
        validation_alias=AliasChoices("originalFilename", "original_filename", "filename"),
        description="Original uploaded filename"
    )
    mime_type: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("mimeType", "mime_type"),
        description="File MIME type"
    )
    file_size_bytes: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("fileSizeBytes", "file_size_bytes"),
        description="File size in bytes"
    )
    file_hash: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("fileHash", "file_hash"),
        description="SHA-256 or MD5 hash of uploaded file"
    )
    organization_slug: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("organizationSlug", "organization_slug"),
        description="Organization slug or code"
    )
    organization_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("organizationId", "organization_id"),
        description="Dataverse account GUID"
    )
    submitted_by: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("submittedBy", "submitted_by"),
        description="User email or identifier who submitted the file"
    )
    submitted_at: Optional[datetime] = Field(
        default=None,
        validation_alias=AliasChoices("submittedAt", "submitted_at"),
        description="Submission timestamp"
    )
