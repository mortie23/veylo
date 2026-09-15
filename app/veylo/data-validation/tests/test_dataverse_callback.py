from models.validation_result import ValidationErrorDetail
from services.dataverse_callback import (
    STATUS_FAILED,
    STATUS_PROCESSED,
    STATUS_VALIDATING,
    DataverseCallback,
    _LOCAL_MOCK_STORE,
)


def test_dataverse_mock_status_update():
    callback = DataverseCallback(dataverse_url="")
    submission_id = "test-sub-100"

    # Validating
    callback.update_submission_status(submission_id, STATUS_VALIDATING, summary="Validating...")
    assert _LOCAL_MOCK_STORE[submission_id]["vey_submissionstatus"] == STATUS_VALIDATING

    # Processed
    callback.update_submission_status(submission_id, STATUS_PROCESSED, summary="All rows passed")
    assert _LOCAL_MOCK_STORE[submission_id]["vey_submissionstatus"] == STATUS_PROCESSED
    assert _LOCAL_MOCK_STORE[submission_id]["vey_name"] == "All rows passed"


def test_dataverse_mock_report_errors():
    callback = DataverseCallback(dataverse_url="")
    submission_id = "test-sub-200"

    errors = [
        ValidationErrorDetail(
            row_number=5,
            column_name="return_date",
            error_code="TYPE_CAST_FAILED",
            error_message="Invalid date format",
            raw_value="31/13/2026",
        ),
        ValidationErrorDetail(
            row_number=12,
            column_name="country_code",
            error_code="CODE_NOT_FOUND",
            error_message="Code XYZ not found",
            raw_value="XYZ",
        )
    ]

    count = callback.report_errors(submission_id, errors)
    assert count == 2
    stored_errors = _LOCAL_MOCK_STORE[submission_id]["errors"]
    assert len(stored_errors) == 2
    assert stored_errors[0]["error_code"] == "TYPE_CAST_FAILED"
    assert stored_errors[1]["column_name"] == "country_code"
