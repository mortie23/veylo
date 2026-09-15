import pandas as pd
from datetime import date
from services.validation_service import ValidationEngine


def test_validate_all_valid_rows(sample_customer_returns_contract):
    df = pd.DataFrame([
        {
            "Return ID": "101",
            "Return Date": "2026-09-11",
            "Country": "AUS",
            "Email": "alice@acme.com",
            "Amount": "50.25",
        },
        {
            "Return ID": "102",
            "Return Date": "2026-09-12",
            "Country": "USA",
            "Email": "bob@acme.com",
            "Amount": "1200.00",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_customer_returns_contract)

    assert result.is_valid is True
    assert result.status == "Processed"
    assert len(result.errors) == 0
    assert result.total_rows == 2
    assert result.failed_rows_count == 0
    assert transformed_df is not None

    # Verify column renaming and type casting
    assert "return_id" in transformed_df.columns
    assert "return_date" in transformed_df.columns
    assert "country_code" in transformed_df.columns
    assert "customer_email" in transformed_df.columns
    assert "refund_amount" in transformed_df.columns

    # Verify code management remapping (AUS -> AU, USA -> US)
    assert transformed_df.iloc[0]["country_code"] == "AU"
    assert transformed_df.iloc[1]["country_code"] == "US"
    assert transformed_df.iloc[0]["return_date"] == date(2026, 9, 11)


def test_validate_missing_required_column(sample_customer_returns_contract):
    # Omit "Return Date" column
    df = pd.DataFrame([
        {
            "Return ID": "101",
            "Country": "AUS",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_customer_returns_contract)

    assert result.is_valid is False
    assert result.status == "Failed"
    assert transformed_df is None
    assert any(e.error_code == "MISSING_COLUMN" for e in result.errors)
    assert any("Return Date" in e.error_message for e in result.errors)


def test_validate_null_violation(sample_customer_returns_contract):
    # return_id is non-nullable, provide empty value
    df = pd.DataFrame([
        {
            "Return ID": "",
            "Return Date": "2026-09-11",
            "Country": "AUS",
            "Email": "alice@acme.com",
            "Amount": "50.25",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_customer_returns_contract)

    assert result.is_valid is False
    assert transformed_df is None
    null_err = next(e for e in result.errors if e.error_code == "NULL_VIOLATION")
    assert null_err.column_name == "return_id"
    assert null_err.row_number == 1


def test_validate_type_cast_failure(sample_customer_returns_contract):
    # Invalid date "31/13/2026"
    df = pd.DataFrame([
        {
            "Return ID": "101",
            "Return Date": "31/13/2026",
            "Country": "AUS",
            "Email": "alice@acme.com",
            "Amount": "50.25",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_customer_returns_contract)

    assert result.is_valid is False
    type_err = next(e for e in result.errors if e.error_code == "TYPE_CAST_FAILED")
    assert type_err.column_name == "return_date"
    assert type_err.raw_value == "31/13/2026"


def test_validate_code_management_lookup(sample_customer_returns_contract):
    # Invalid country "XYZ"
    df = pd.DataFrame([
        {
            "Return ID": "101",
            "Return Date": "2026-09-11",
            "Country": "XYZ",
            "Email": "alice@acme.com",
            "Amount": "50.25",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_customer_returns_contract)

    assert result.is_valid is False
    code_err = next(e for e in result.errors if e.error_code == "CODE_NOT_FOUND")
    assert code_err.column_name == "country_code"
    assert code_err.raw_value == "XYZ"


def test_validate_dq_rules_regex_and_range(sample_customer_returns_contract):
    # Bad email and amount > 10000
    df = pd.DataFrame([
        {
            "Return ID": "101",
            "Return Date": "2026-09-11",
            "Country": "AUS",
            "Email": "not-an-email",
            "Amount": "15000",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_customer_returns_contract)

    assert result.is_valid is False
    dq_errors = [e for e in result.errors if e.error_code == "DQ_RULE_FAILED"]
    assert len(dq_errors) == 2
    assert any(e.column_name == "customer_email" for e in dq_errors)
    assert any(e.column_name == "refund_amount" for e in dq_errors)
    assert "1 of 1 rows failed validation across 2 field(s)" in result.summary
