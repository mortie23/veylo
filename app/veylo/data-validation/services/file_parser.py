import io
import logging
import os
import urllib.parse
from typing import Optional
import pandas as pd
import requests

logger = logging.getLogger(__name__)


class FileParserError(Exception):
    """Raised when file streaming or parsing fails."""
    pass


class FileParser:
    """Service to stream files via HTTP/SAS and parse CSV/XLSX formats into pandas DataFrames."""

    @staticmethod
    def stream_file_from_sas(sas_url: str, timeout: int = 60) -> bytes:
        """
        Streams file contents from an Azure Blob Storage read-only SAS URL.
        No Azure SDK is required on the GCP side as the SAS URL is a pre-signed HTTPS URL.
        """
        try:
            parsed = urllib.parse.urlparse(sas_url)
            if parsed.scheme != "https":
                raise FileParserError(f"Insecure SAS URL scheme '{parsed.scheme}'; HTTPS is required.")

            hostname = (parsed.hostname or "").lower()
            if not (hostname.endswith(".blob.core.windows.net") or hostname in ("localhost", "127.0.0.1", "testserver")):
                raise FileParserError(f"Untrusted SAS URL host '{hostname}'; must be an Azure Blob Storage domain.")

            logger.info("Initiating streaming download from SAS URL")
            with requests.get(sas_url, stream=True, timeout=timeout) as response:
                if response.status_code != 200:
                    raise FileParserError(
                        f"Failed to download blob from SAS URL. HTTP Status: {response.status_code}, Response: {response.text[:200]}"
                    )
                buffer = io.BytesIO()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        buffer.write(chunk)
                return buffer.getvalue()
        except requests.RequestException as e:
            logger.error(f"Network error streaming file from SAS URL: {e}")
            raise FileParserError(f"Network error streaming file from SAS URL: {e}") from e

    @staticmethod
    def parse(
        content: bytes,
        filename: str,
        mime_type: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Parses binary content of CSV or Excel file into a pandas DataFrame.
        Reads all columns initially as strings to preserve raw values for contract validation.
        """
        if not content:
            raise FileParserError("File content is empty.")

        ext = os.path.splitext(filename.lower())[1]

        if ext == ".csv" or (mime_type and "csv" in mime_type.lower()):
            return FileParser._parse_csv(content)
        elif ext in (".xlsx", ".xls") or (mime_type and ("spreadsheet" in mime_type.lower() or "excel" in mime_type.lower())):
            return FileParser._parse_excel(content)
        else:
            raise FileParserError(f"Unsupported file format '{ext}' for file '{filename}'. Expected CSV or XLSX.")

    @staticmethod
    def _parse_csv(content: bytes) -> pd.DataFrame:
        encodings = ["utf-8-sig", "utf-8", "latin1", "cp1252"]
        last_err = None

        for enc in encodings:
            try:
                df = pd.read_csv(
                    io.BytesIO(content),
                    encoding=enc,
                    dtype=str,
                    keep_default_na=False,
                    skipinitialspace=True,
                )
                df.columns = [str(c).strip() for c in df.columns]
                return df
            except Exception as e:
                last_err = e
                continue

        raise FileParserError(f"Failed to parse CSV with supported encodings: {last_err}") from last_err

    @staticmethod
    def _parse_excel(content: bytes) -> pd.DataFrame:
        try:
            df = pd.read_excel(
                io.BytesIO(content),
                dtype=str,
                keep_default_na=False,
                engine="openpyxl",
            )
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            logger.error(f"Failed to parse Excel file: {e}")
            raise FileParserError(f"Failed to parse Excel file: {e}") from e
