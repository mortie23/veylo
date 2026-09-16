import io
import pandas as pd
import pytest
from services.file_parser import FileParser, FileParserError


def test_parse_csv_basic():
    csv_bytes = b"Return ID,Return Date,Country\n101,2026-09-11,AUS\n102,2026-09-12,USA\n"
    df = FileParser.parse(csv_bytes, "returns.csv")
    assert len(df) == 2
    assert list(df.columns) == ["Return ID", "Return Date", "Country"]
    assert df.iloc[0]["Return ID"] == "101"
    assert df.iloc[1]["Country"] == "USA"


def test_parse_csv_with_utf8_bom():
    bom_csv = b"\xef\xbb\xbfReturn ID,Return Date\n201,2026-09-11\n"
    df = FileParser.parse(bom_csv, "bom.csv")
    assert len(df) == 1
    assert "Return ID" in df.columns


def test_parse_excel_basic():
    # Create an in-memory Excel workbook
    output = io.BytesIO()
    sample_df = pd.DataFrame({
        "Return ID": ["301", "302"],
        "Amount": ["45.50", "99.00"]
    })
    sample_df.to_excel(output, index=False, engine="openpyxl")
    excel_bytes = output.getvalue()

    df = FileParser.parse(excel_bytes, "returns.xlsx")
    assert len(df) == 2
    assert list(df.columns) == ["Return ID", "Amount"]
    assert df.iloc[0]["Return ID"] == "301"


def test_parse_empty_content():
    with pytest.raises(FileParserError, match="File content is empty"):
        FileParser.parse(b"", "test.csv")


def test_parse_unsupported_format():
    with pytest.raises(FileParserError, match="Unsupported file format"):
        FileParser.parse(b"hello world", "test.pdf")


def test_stream_sas_invalid_scheme():
    with pytest.raises(FileParserError, match="Insecure SAS URL scheme"):
        FileParser.stream_file_from_sas("http://mystorageaccount.blob.core.windows.net/test.csv")


def test_stream_sas_untrusted_host_metadata():
    with pytest.raises(FileParserError, match="Untrusted SAS URL host"):
        FileParser.stream_file_from_sas("https://169.254.169.254/computeMetadata/v1/")


def test_stream_sas_untrusted_host_arbitrary():
    with pytest.raises(FileParserError, match="Untrusted SAS URL host"):
        FileParser.stream_file_from_sas("https://evil-host.attacker.com/blob.csv")

