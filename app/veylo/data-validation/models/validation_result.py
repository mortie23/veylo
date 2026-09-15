from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ValidationErrorDetail(BaseModel):
    row_number: Optional[int] = Field(
        default=None,
        description="1-based row number in the uploaded file where validation failed"
    )
    column_name: Optional[str] = Field(
        default=None,
        description="Source or target column name"
    )
    error_code: str = Field(
        ...,
        description="Standardized error code (e.g., TYPE_CAST_FAILED, CODE_NOT_FOUND, NULL_VIOLATION, DQ_RULE_FAILED, STRUCTURE_ERROR)"
    )
    error_message: str = Field(
        ...,
        description="Descriptive explanation of the validation failure"
    )
    raw_value: Optional[str] = Field(
        default=None,
        description="Raw string value from the input file"
    )


class ValidationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    is_valid: bool = Field(
        ...,
        description="True if file passed all required contract rules without ERROR-severity failures"
    )
    status: str = Field(
        ...,
        description="Status string: 'Processed' or 'Failed'"
    )
    summary: str = Field(
        ...,
        description="Human-readable summary of validation outcome"
    )
    errors: List[ValidationErrorDetail] = Field(
        default_factory=list,
        description="List of row-level and structural validation errors"
    )
    total_rows: int = Field(
        default=0,
        description="Total data rows evaluated"
    )
    failed_rows_count: int = Field(
        default=0,
        description="Number of distinct rows that contained errors"
    )
    failed_fields_count: int = Field(
        default=0,
        description="Number of distinct fields that contained errors"
    )
