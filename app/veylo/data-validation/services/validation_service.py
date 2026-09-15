from datetime import date, datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from models.orm import Attribute, DataContract, Entity
from models.validation_result import ValidationErrorDetail, ValidationResult

logger = logging.getLogger(__name__)


class ValidationEngine:
    """Core validation engine implementing structure, type, code set, and DQ rule validations."""

    def __init__(self, reject_on_error: bool = True):
        self.reject_on_error = reject_on_error

    def validate(
        self,
        df: pd.DataFrame,
        contract: DataContract,
        entity_name: Optional[str] = None
    ) -> Tuple[ValidationResult, Optional[pd.DataFrame]]:
        """
        Validates a parsed DataFrame against the specified DataContract.

        Returns:
            Tuple of (ValidationResult, transformed_df).
            If valid, transformed_df contains columns renamed and cast to target types.
            If invalid, transformed_df is None.
        """
        total_rows = len(df)
        errors: List[ValidationErrorDetail] = []
        failed_row_indices: Set[int] = set()
        failed_field_names: Set[str] = set()

        # 1. Select the relevant Entity definition
        entity = self._resolve_entity(contract, entity_name)
        if not entity:
            err = ValidationErrorDetail(
                row_number=None,
                column_name=None,
                error_code="ENTITY_NOT_FOUND",
                error_message=f"No matching entity configuration found in contract '{contract.contract_name}'",
                raw_value=None,
            )
            return ValidationResult(
                is_valid=False,
                status="Failed",
                summary="Entity configuration not found in data contract.",
                errors=[err],
                total_rows=total_rows,
                failed_rows_count=0,
                failed_fields_count=0,
            ), None

        # 2. Structural Validation: check all required source fields exist
        missing_columns: List[str] = []
        for attr in entity.attributes:
            if attr.src_field_name not in df.columns:
                missing_columns.append(attr.src_field_name)

        if missing_columns:
            for col in missing_columns:
                errors.append(
                    ValidationErrorDetail(
                        row_number=None,
                        column_name=col,
                        error_code="MISSING_COLUMN",
                        error_message=f"Required source column '{col}' is missing from the uploaded file.",
                        raw_value=None,
                    )
                )
                failed_field_names.add(col)

            summary = f"Structure validation failed: missing {len(missing_columns)} required column(s): {', '.join(missing_columns)}"
            return ValidationResult(
                is_valid=False,
                status="Failed",
                summary=summary,
                errors=errors,
                total_rows=total_rows,
                failed_rows_count=0,
                failed_fields_count=len(failed_field_names),
            ), None

        # 3. Rename columns from src_field_name -> tgt_field_name
        rename_map = {attr.src_field_name: attr.tgt_field_name for attr in entity.attributes}
        working_df = df.copy().rename(columns=rename_map)

        # 4. Row-level validation across all attributes
        # Pre-build code management lookup sets for performance
        code_lookups: Dict[str, Dict[str, str]] = {}
        for attr in entity.attributes:
            if attr.code_management:
                # Map source_code -> target_code
                mapping = {}
                for cm in attr.code_management:
                    mapping[cm.source_code.strip()] = cm.target_code or cm.source_code
                code_lookups[attr.tgt_field_name] = mapping

        # Iterate through rows and validate
        for row_idx, row in working_df.iterrows():
            row_num = row_idx + 1  # 1-based indexing for business users

            for attr in entity.attributes:
                field_name = attr.tgt_field_name
                raw_val = row.get(field_name)

                # Determine if value is empty/null
                is_empty = raw_val is None or (isinstance(raw_val, str) and raw_val.strip() == "") or pd.isna(raw_val)
                str_val = "" if is_empty else str(raw_val).strip()

                # Rule A: Nullability check
                if not attr.is_nullable and is_empty:
                    errors.append(
                        ValidationErrorDetail(
                            row_number=row_num,
                            column_name=field_name,
                            error_code="NULL_VIOLATION",
                            error_message=f"Field '{field_name}' is not nullable and cannot be empty.",
                            raw_value=str(raw_val) if raw_val is not None else "",
                        )
                    )
                    failed_row_indices.add(row_num)
                    failed_field_names.add(field_name)
                    continue

                if is_empty:
                    # Optional field is empty; skip type casting and DQ rules
                    continue

                # Rule B: Type casting validation
                cast_ok, cast_err = self._validate_type_casting(str_val, attr.tgt_data_type)
                if not cast_ok:
                    errors.append(
                        ValidationErrorDetail(
                            row_number=row_num,
                            column_name=field_name,
                            error_code="TYPE_CAST_FAILED",
                            error_message=cast_err or f"Cannot cast '{str_val}' to {attr.tgt_data_type}.",
                            raw_value=str_val,
                        )
                    )
                    failed_row_indices.add(row_num)
                    failed_field_names.add(field_name)
                    continue

                # Rule C: Code set lookup validation
                if field_name in code_lookups:
                    allowed_codes = code_lookups[field_name]
                    if str_val not in allowed_codes:
                        code_system = attr.code_management[0].code_system_name or "code set"
                        errors.append(
                            ValidationErrorDetail(
                                row_number=row_num,
                                column_name=field_name,
                                error_code="CODE_NOT_FOUND",
                                error_message=f"Value '{str_val}' is not a valid code in code set '{code_system}'.",
                                raw_value=str_val,
                            )
                        )
                        failed_row_indices.add(row_num)
                        failed_field_names.add(field_name)
                        continue
                    else:
                        # Remap to target_code if different
                        target_code = allowed_codes[str_val]
                        if target_code != str_val:
                            working_df.at[row_idx, field_name] = target_code

                # Rule D: Data Quality rules
                if attr.data_quality_rules:
                    for dq in attr.data_quality_rules:
                        dq_ok, dq_msg = self._validate_dq_rule(str_val, field_name, dq.rule_type, dq.rule_value, dq.error_message_template)
                        if not dq_ok:
                            if dq.severity.upper() == "ERROR":
                                errors.append(
                                    ValidationErrorDetail(
                                        row_number=row_num,
                                        column_name=field_name,
                                        error_code="DQ_RULE_FAILED",
                                        error_message=dq_msg,
                                        raw_value=str_val,
                                    )
                                )
                                failed_row_indices.add(row_num)
                                failed_field_names.add(field_name)

        # 5. Check if any errors occurred
        has_errors = len(errors) > 0
        failed_rows_count = len(failed_row_indices)
        failed_fields_count = len(failed_field_names)

        if has_errors and self.reject_on_error:
            summary = f"{failed_rows_count} of {total_rows} rows failed validation across {failed_fields_count} field(s)."
            return ValidationResult(
                is_valid=False,
                status="Failed",
                summary=summary,
                errors=errors,
                total_rows=total_rows,
                failed_rows_count=failed_rows_count,
                failed_fields_count=failed_fields_count,
            ), None

        # 6. Success: Transform and cast DataFrame to BigQuery-compatible types
        transformed_df = self._cast_dataframe(working_df, entity.attributes)

        summary = f"All {total_rows} rows successfully validated against contract '{contract.contract_name}'."
        return ValidationResult(
            is_valid=True,
            status="Processed",
            summary=summary,
            errors=[],
            total_rows=total_rows,
            failed_rows_count=0,
            failed_fields_count=0,
        ), transformed_df

    def _resolve_entity(self, contract: DataContract, entity_name: Optional[str] = None) -> Optional[Entity]:
        if not contract.entities:
            return None
        if not entity_name:
            # Default to first entity for single-entity PoC
            return contract.entities[0]
        for e in contract.entities:
            if e.tgt_entity_name == entity_name or e.src_entity_name == entity_name:
                return e
        return contract.entities[0]

    def _validate_type_casting(self, val: str, tgt_type: str) -> Tuple[bool, Optional[str]]:
        t = tgt_type.upper()
        if t in ("STRING", "TEXT"):
            return True, None

        elif t in ("INT64", "INTEGER", "INT"):
            # Check integer representation
            if not re.fullmatch(r"^-?\d+$", val):
                return False, f"Cannot cast '{val}' to {t} (expected whole integer, e.g. 42)"
            return True, None

        elif t in ("FLOAT64", "FLOAT", "NUMERIC", "DECIMAL"):
            try:
                float(val)
                return True, None
            except ValueError:
                return False, f"Cannot cast '{val}' to {t} (expected decimal number, e.g. 19.99)"

        elif t in ("BOOL", "BOOLEAN"):
            if val.lower() not in ("true", "false", "1", "0", "yes", "no", "t", "f"):
                return False, f"Cannot cast '{val}' to BOOL (expected true/false, 1/0, yes/no)"
            return True, None

        elif t == "DATE":
            # Match ISO 8601 YYYY-MM-DD
            if not re.fullmatch(r"^\d{4}-\d{2}-\d{2}$", val):
                return False, f"Cannot cast '{val}' to DATE (expected ISO 8601 format YYYY-MM-DD)"
            try:
                datetime.strptime(val, "%Y-%m-%d")
                return True, None
            except ValueError:
                return False, f"Value '{val}' is not a valid calendar date"

        elif t in ("TIMESTAMP", "DATETIME"):
            # Try ISO 8601 formats
            parsed = False
            for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    datetime.strptime(val, fmt)
                    parsed = True
                    break
                except ValueError:
                    continue
            if not parsed:
                try:
                    datetime.fromisoformat(val)
                    parsed = True
                except ValueError:
                    pass

            if not parsed:
                return False, f"Cannot cast '{val}' to TIMESTAMP (expected ISO 8601 format, e.g. YYYY-MM-DDTHH:MM:SSZ)"
            return True, None

        return True, None

    def _validate_dq_rule(
        self,
        val: str,
        field_name: str,
        rule_type: str,
        rule_value: Optional[str],
        error_template: Optional[str]
    ) -> Tuple[bool, str]:
        rule_type = rule_type.upper()

        if rule_type == "REGEX":
            if rule_value:
                try:
                    if not re.search(rule_value, val):
                        msg = error_template or f"Field '{field_name}' must match pattern '{rule_value}'"
                        return False, msg.replace("{field}", field_name).replace("{rule_value}", rule_value).replace("{value}", val)
                except re.error as e:
                    logger.warning(f"Invalid regex rule pattern '{rule_value}': {e}")

        elif rule_type == "RANGE":
            if rule_value:
                try:
                    cfg = json.loads(rule_value)
                    num_val = float(val)
                    min_val = cfg.get("min")
                    max_val = cfg.get("max")
                    if min_val is not None and num_val < min_val:
                        msg = error_template or f"Field '{field_name}' value '{val}' is below minimum {min_val}"
                        return False, msg.replace("{field}", field_name).replace("{rule_value}", rule_value).replace("{value}", val)
                    if max_val is not None and num_val > max_val:
                        msg = error_template or f"Field '{field_name}' value '{val}' exceeds maximum {max_val}"
                        return False, msg.replace("{field}", field_name).replace("{rule_value}", rule_value).replace("{value}", val)
                except (ValueError, json.JSONDecodeError):
                    pass

        elif rule_type == "LENGTH":
            if rule_value:
                try:
                    cfg = json.loads(rule_value) if rule_value.startswith("{") else {"max": int(rule_value)}
                    str_len = len(val)
                    min_len = cfg.get("min")
                    max_len = cfg.get("max")
                    if min_len is not None and str_len < min_len:
                        msg = error_template or f"Field '{field_name}' length ({str_len}) is below minimum length {min_len}"
                        return False, msg.replace("{field}", field_name).replace("{rule_value}", rule_value).replace("{value}", val)
                    if max_len is not None and str_len > max_len:
                        msg = error_template or f"Field '{field_name}' length ({str_len}) exceeds maximum length {max_len}"
                        return False, msg.replace("{field}", field_name).replace("{rule_value}", rule_value).replace("{value}", val)
                except (ValueError, json.JSONDecodeError):
                    pass

        elif rule_type == "ENUM":
            if rule_value:
                try:
                    allowed = json.loads(rule_value) if rule_value.startswith("[") else [s.strip() for s in rule_value.split(",")]
                    if val not in allowed:
                        msg = error_template or f"Field '{field_name}' value '{val}' is not in allowed list: {allowed}"
                        return False, msg.replace("{field}", field_name).replace("{rule_value}", rule_value).replace("{value}", val)
                except json.JSONDecodeError:
                    pass

        return True, ""

    def _cast_dataframe(self, df: pd.DataFrame, attributes: List[Attribute]) -> pd.DataFrame:
        """Casts columns to native types suitable for BigQuery loading."""
        result = pd.DataFrame()
        for attr in attributes:
            col = attr.tgt_field_name
            t = attr.tgt_data_type.upper()
            if col not in df.columns:
                continue

            series = df[col]

            if t in ("INT64", "INTEGER", "INT"):
                result[col] = pd.to_numeric(series.replace("", None), errors="coerce").astype("Int64")
            elif t in ("FLOAT64", "FLOAT", "NUMERIC", "DECIMAL"):
                result[col] = pd.to_numeric(series.replace("", None), errors="coerce").astype("Float64")
            elif t in ("BOOL", "BOOLEAN"):
                true_vals = {"true", "1", "yes", "t"}
                result[col] = series.apply(
                    lambda x: (x.strip().lower() in true_vals) if (x is not None and str(x).strip() != "") else None
                ).astype("boolean")
            elif t == "DATE":
                result[col] = pd.to_datetime(series.replace("", None), errors="coerce").dt.date
            elif t in ("TIMESTAMP", "DATETIME"):
                result[col] = pd.to_datetime(series.replace("", None), errors="coerce", utc=True)
            else:
                result[col] = series.replace("", None).astype(str)

        return result
