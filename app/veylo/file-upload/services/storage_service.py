import datetime
import logging
import os
from typing import Optional
from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    generate_blob_sas
)

logger = logging.getLogger(__name__)


class StorageService:
    """Manages Azure Blob Storage operations using Managed Identity and User Delegation SAS tokens."""

    def __init__(
        self,
        account_name: Optional[str] = None,
        container_name: Optional[str] = None
    ):
        self.account_name = account_name or os.environ.get("STORAGE_ACCOUNT_NAME", "")
        self.container_name = container_name or os.environ.get("BLOB_CONTAINER_NAME", "submissions")
        self.credential = DefaultAzureCredential()
        self.endpoint_url = f"https://{self.account_name}.blob.core.windows.net"

        self._client: Optional[BlobServiceClient] = None

    @property
    def client(self) -> BlobServiceClient:
        if not self._client:
            if not self.account_name:
                raise ValueError("STORAGE_ACCOUNT_NAME is not configured.")
            self._client = BlobServiceClient(
                account_url=self.endpoint_url,
                credential=self.credential
            )
        return self._client

    def generate_upload_sas(self, blob_name: str, duration_minutes: int = 15) -> str:
        """
        Generate a write-only User Delegation SAS URL for uploading a file directly to Blob Storage.
        Does not require account keys.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        # Give a small clock-skew buffer on the delegation key
        user_delegation_key = self.client.get_user_delegation_key(
            key_start_time=now - datetime.timedelta(minutes=5),
            key_expiry_time=now + datetime.timedelta(minutes=duration_minutes + 10)
        )

        sas_token = generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(write=True, create=True),
            expiry=now + datetime.timedelta(minutes=duration_minutes)
        )

        blob_url = f"{self.endpoint_url}/{self.container_name}/{blob_name}"
        return f"{blob_url}?{sas_token}"

    def generate_download_sas(
        self,
        blob_name: str,
        filename: str,
        duration_minutes: int = 15
    ) -> str:
        """
        Generate a read-only User Delegation SAS URL for downloading a file securely.
        Forces Content-Disposition: attachment to prevent browser-based XSS attacks.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        user_delegation_key = self.client.get_user_delegation_key(
            key_start_time=now - datetime.timedelta(minutes=5),
            key_expiry_time=now + datetime.timedelta(minutes=duration_minutes + 10)
        )

        clean_filename = filename.replace('"', '').replace('\n', '').replace('\r', '')

        sas_token = generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=now + datetime.timedelta(minutes=duration_minutes),
            content_disposition=f'attachment; filename="{clean_filename}"'
        )

        blob_url = f"{self.endpoint_url}/{self.container_name}/{blob_name}"
        return f"{blob_url}?{sas_token}"
