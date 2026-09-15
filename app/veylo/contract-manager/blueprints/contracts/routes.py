import csv
import io
import json
import re
from datetime import datetime, timezone
from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from blueprints.contracts import contracts_bp
from database import SessionLocal
from models.orm import Attribute, CodeManagement, DataContract, DataQuality, Entity
from seed_data import seed_sample_contracts


@contracts_bp.route("/")
def index():
    """Contracts Catalog view."""
    db = SessionLocal()
    try:
        contracts = (
            db.query(DataContract)
            .options(joinedload(DataContract.entities).joinedload(Entity.attributes))
            .order_by(DataContract.created_at.desc())
            .all()
        )

        total_contracts = len(contracts)
        active_contracts = sum(1 for c in contracts if c.is_active)
        total_entities = sum(len(c.entities) for c in contracts)
        total_rules = (
            db.query(func.count(DataQuality.data_quality_id)).scalar() or 0
        ) + (
            db.query(func.count(CodeManagement.code_management_id)).scalar() or 0
        )

        stats = {
            "total_contracts": total_contracts,
            "active_contracts": active_contracts,
            "total_entities": total_entities,
            "total_rules": total_rules,
        }

        return render_template(
            "contracts/index.html",
            contracts=contracts,
            stats=stats,
            config=current_app.config["APP_SETTINGS"],
        )
    finally:
        db.close()


@contracts_bp.route("/contracts/new", methods=["GET"])
def new():
    """Renders the Contract Builder wizard."""
    return render_template(
        "contracts/new.html",
        config=current_app.config["APP_SETTINGS"],
    )


@contracts_bp.route("/contracts", methods=["POST"])
def create():
    """Handles submission of the Contract Builder wizard."""
    form = request.form
    contract_name = form.get("contract_name", "").strip().lower()
    contract_version = form.get("contract_version", "v1.0.0").strip()
    data_steward_email = form.get("data_steward_email", "").strip() or None
    tgt_entity_name = form.get("tgt_entity_name", "").strip().lower()
    tgt_dataset = form.get("tgt_dataset", "veylo_bronze").strip()

    if not contract_name or not tgt_entity_name:
        flash("Contract Name and Target Entity Name are required.", "danger")
        return redirect(url_for("contracts.new"))

    db = SessionLocal()
    try:
        # Check duplicate contract_name + version
        existing = db.query(DataContract).filter_by(
            contract_name=contract_name,
            contract_version=contract_version,
        ).first()
        if existing:
            flash(f"Contract '{contract_name}' ({contract_version}) already exists.", "danger")
            return redirect(url_for("contracts.new"))

        contract = DataContract(
            contract_name=contract_name,
            contract_version=contract_version,
            data_steward_email=data_steward_email,
            is_active=True,
        )
        db.add(contract)
        db.flush()

        entity = Entity(
            data_contract_id=contract.data_contract_id,
            src_entity_name=tgt_entity_name,
            tgt_entity_name=tgt_entity_name,
            tgt_dataset=tgt_dataset,
        )
        db.add(entity)
        db.flush()

        # Parse dynamic attributes from form fields: attributes[i][...]
        attr_dict = {}
        for key, value in form.items():
            match = re.match(r"attributes\[(\d+)\]\[(\w+)\]", key)
            if match:
                idx, field = match.groups()
                idx = int(idx)
                if idx not in attr_dict:
                    attr_dict[idx] = {}
                attr_dict[idx][field] = value.strip()

        for idx in sorted(attr_dict.keys()):
            item = attr_dict[idx]
            src_field = item.get("src_field_name")
            tgt_field = item.get("tgt_field_name")
            tgt_type = item.get("tgt_data_type", "STRING")
            is_pk = item.get("is_pk") in ("true", "1", "on")
            is_nullable = item.get("is_nullable") in ("true", "1", "on")

            if src_field and tgt_field:
                db.add(Attribute(
                    entity_id=entity.entity_id,
                    src_field_name=src_field,
                    tgt_field_name=tgt_field,
                    tgt_data_type=tgt_type,
                    is_pk=is_pk,
                    is_nullable=is_nullable,
                    ordinal_position=idx,
                ))

        db.commit()
        flash(f"Data contract '{contract_name}' successfully created.", "success")
        return redirect(url_for("contracts.detail", contract_id=contract.data_contract_id))
    except Exception as ex:
        db.rollback()
        flash(f"Failed to create contract: {ex}", "danger")
        return redirect(url_for("contracts.new"))
    finally:
        db.close()


@contracts_bp.route("/contracts/<contract_id>")
def detail(contract_id: str):
    """Detailed schema and rules inspection for a single contract."""
    db = SessionLocal()
    try:
        contract = (
            db.query(DataContract)
            .options(
                joinedload(DataContract.entities)
                .joinedload(Entity.attributes)
                .joinedload(Attribute.data_quality_rules),
                joinedload(DataContract.entities)
                .joinedload(Entity.attributes)
                .joinedload(Attribute.code_management),
            )
            .filter(DataContract.data_contract_id == contract_id)
            .first()
        )

        if not contract:
            flash("Contract not found.", "danger")
            return redirect(url_for("contracts.index"))

        return render_template(
            "contracts/detail.html",
            contract=contract,
            config=current_app.config["APP_SETTINGS"],
        )
    finally:
        db.close()


@contracts_bp.route("/contracts/<contract_id>/toggle", methods=["POST"])
def toggle_status(contract_id: str):
    """Toggles active/inactive status."""
    db = SessionLocal()
    try:
        contract = db.query(DataContract).filter_by(data_contract_id=contract_id).first()
        if contract:
            contract.is_active = not contract.is_active
            contract.updated_at = datetime.now(timezone.utc)
            db.commit()
            state = "activated" if contract.is_active else "deactivated"
            flash(f"Contract '{contract.contract_name}' has been {state}.", "info")
        return redirect(url_for("contracts.index"))
    finally:
        db.close()


@contracts_bp.route("/contracts/<contract_id>/delete", methods=["POST"])
def delete_contract(contract_id: str):
    """Deletes a contract and its entity/attribute definitions."""
    db = SessionLocal()
    try:
        contract = db.query(DataContract).filter_by(data_contract_id=contract_id).first()
        if contract:
            name = contract.contract_name
            db.delete(contract)
            db.commit()
            flash(f"Contract '{name}' deleted.", "warning")
        return redirect(url_for("contracts.index"))
    finally:
        db.close()


@contracts_bp.route("/contracts/seed", methods=["POST"])
def seed_data_route():
    """Seeds sample demo contracts into local SQLite."""
    settings = current_app.config["APP_SETTINGS"]
    if settings.is_sqlite:
        seed_sample_contracts(force=True)
        flash("Sample contracts successfully seeded into local database.", "success")
    else:
        flash("Seeding is restricted to local development mode.", "warning")
    return redirect(url_for("contracts.index"))


@contracts_bp.route("/contracts/<contract_id>/test", methods=["GET"])
def test_schema(contract_id: str):
    """Renders the interactive schema test workbench."""
    db = SessionLocal()
    try:
        contract = (
            db.query(DataContract)
            .options(
                joinedload(DataContract.entities)
                .joinedload(Entity.attributes)
                .joinedload(Attribute.data_quality_rules),
                joinedload(DataContract.entities)
                .joinedload(Entity.attributes)
                .joinedload(Attribute.code_management),
            )
            .filter(DataContract.data_contract_id == contract_id)
            .first()
        )
        if not contract:
            flash("Contract not found.", "danger")
            return redirect(url_for("contracts.index"))

        return render_template(
            "contracts/test_schema.html",
            contract=contract,
            config=current_app.config["APP_SETTINGS"],
        )
    finally:
        db.close()


@contracts_bp.route("/contracts/<contract_id>/test", methods=["POST"])
def run_test_schema(contract_id: str):
    """Executes sample CSV validation simulation against contract rules."""
    sample_csv = request.form.get("sample_csv", "").strip()

    db = SessionLocal()
    try:
        contract = (
            db.query(DataContract)
            .options(
                joinedload(DataContract.entities)
                .joinedload(Entity.attributes)
                .joinedload(Attribute.data_quality_rules),
                joinedload(DataContract.entities)
                .joinedload(Entity.attributes)
                .joinedload(Attribute.code_management),
            )
            .filter(DataContract.data_contract_id == contract_id)
            .first()
        )
        if not contract or not contract.entities:
            flash("Contract entity definition not found.", "danger")
            return redirect(url_for("contracts.index"))

        entity = contract.entities[0]
        attributes = entity.attributes
        attr_by_src = {attr.src_field_name: attr for attr in attributes}

        # Parse CSV
        reader = csv.DictReader(io.StringIO(sample_csv))
        errors = []
        preview_rows = []
        row_count = 0

        # Check required columns
        csv_fields = set(reader.fieldnames or [])
        for attr in attributes:
            if attr.src_field_name not in csv_fields:
                errors.append({
                    "row_number": None,
                    "column_name": attr.src_field_name,
                    "error_code": "MISSING_COLUMN",
                    "error_message": f"Expected source column '{attr.src_field_name}' not found in CSV headers",
                })

        if not errors:
            for row_idx, row in enumerate(reader, start=1):
                row_count += 1
                transformed_row = {}

                for attr in attributes:
                    val = row.get(attr.src_field_name, "")
                    tgt_col = attr.tgt_field_name

                    # 1. Nullability check
                    if not attr.is_nullable and (val is None or str(val).strip() == ""):
                        errors.append({
                            "row_number": row_idx,
                            "column_name": attr.src_field_name,
                            "error_code": "NOT_NULL_VIOLATION",
                            "error_message": f"Field '{attr.src_field_name}' is required and cannot be blank",
                        })
                        continue

                    if val is None or str(val).strip() == "":
                        transformed_row[tgt_col] = None
                        continue

                    # 2. Type casting simulation
                    clean_val = str(val).strip()
                    try:
                        if attr.tgt_data_type in ("INT64", "INTEGER"):
                            transformed_val = int(clean_val)
                        elif attr.tgt_data_type in ("FLOAT64", "NUMERIC"):
                            transformed_val = float(clean_val)
                        elif attr.tgt_data_type == "DATE":
                            datetime.strptime(clean_val, "%Y-%m-%d")
                            transformed_val = clean_val
                        elif attr.tgt_data_type in ("TIMESTAMP", "DATETIME"):
                            parsed = False
                            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
                                try:
                                    datetime.strptime(clean_val, fmt)
                                    parsed = True
                                    break
                                except ValueError:
                                    continue
                            if not parsed:
                                raise ValueError(f"Cannot parse timestamp '{clean_val}'")
                            transformed_val = clean_val
                        elif attr.tgt_data_type == "BOOL":
                            transformed_val = clean_val.lower() in ("true", "1", "yes")
                        else:
                            transformed_val = clean_val
                        transformed_row[tgt_col] = transformed_val
                    except Exception:
                        errors.append({
                            "row_number": row_idx,
                            "column_name": attr.src_field_name,
                            "error_code": "TYPE_CAST_FAILED",
                            "error_message": f"Cannot cast value '{clean_val}' to target BigQuery type {attr.tgt_data_type}",
                        })
                        continue

                    # 3. Code Management validation & mapping
                    if attr.code_management:
                        code_map = {c.source_code: (c.target_code or c.source_code) for c in attr.code_management}
                        if clean_val not in code_map:
                            errors.append({
                                "row_number": row_idx,
                                "column_name": attr.src_field_name,
                                "error_code": "INVALID_CODE",
                                "error_message": f"Value '{clean_val}' is not in allowed code set: {list(code_map.keys())}",
                            })
                        else:
                            transformed_row[tgt_col] = code_map[clean_val]

                    # 4. Data Quality rules
                    for dq in attr.data_quality_rules:
                        if dq.rule_type == "REGEX" and dq.rule_value:
                            if not re.search(dq.rule_value, clean_val):
                                errors.append({
                                    "row_number": row_idx,
                                    "column_name": attr.src_field_name,
                                    "error_code": "DQ_REGEX_FAILED",
                                    "error_message": dq.error_message_template or f"Value '{clean_val}' failed pattern '{dq.rule_value}'",
                                })
                        elif dq.rule_type == "ENUM" and dq.rule_value:
                            try:
                                allowed = json.loads(dq.rule_value) if dq.rule_value.startswith("[") else [s.strip() for s in dq.rule_value.split(",")]
                                if clean_val not in allowed:
                                    errors.append({
                                        "row_number": row_idx,
                                        "column_name": attr.src_field_name,
                                        "error_code": "DQ_ENUM_INVALID",
                                        "error_message": dq.error_message_template or f"Value '{clean_val}' is not in allowed list: {allowed}",
                                    })
                            except Exception:
                                pass
                        elif dq.rule_type == "RANGE" and dq.rule_value:
                            try:
                                bounds = json.loads(dq.rule_value)
                                num = float(clean_val)
                                if "min" in bounds and num < bounds["min"]:
                                    errors.append({
                                        "row_number": row_idx,
                                        "column_name": attr.src_field_name,
                                        "error_code": "DQ_RANGE_LOW",
                                        "error_message": dq.error_message_template or f"Value {num} is below min bound {bounds['min']}",
                                    })
                                if "max" in bounds and num > bounds["max"]:
                                    errors.append({
                                        "row_number": row_idx,
                                        "column_name": attr.src_field_name,
                                        "error_code": "DQ_RANGE_HIGH",
                                        "error_message": dq.error_message_template or f"Value {num} exceeds max bound {bounds['max']}",
                                    })
                            except Exception:
                                pass
                        elif dq.rule_type == "LENGTH" and dq.rule_value:
                            try:
                                bounds = json.loads(dq.rule_value)
                                length = len(clean_val)
                                if "min" in bounds and length < bounds["min"]:
                                    errors.append({
                                        "row_number": row_idx,
                                        "column_name": attr.src_field_name,
                                        "error_code": "DQ_LENGTH_SHORT",
                                        "error_message": dq.error_message_template or f"Length {length} is shorter than min {bounds['min']}",
                                    })
                                if "max" in bounds and length > bounds["max"]:
                                    errors.append({
                                        "row_number": row_idx,
                                        "column_name": attr.src_field_name,
                                        "error_code": "DQ_LENGTH_LONG",
                                        "error_message": dq.error_message_template or f"Length {length} exceeds max {bounds['max']}",
                                    })
                            except Exception:
                                pass

                preview_rows.append(transformed_row)

        result = {
            "is_valid": len(errors) == 0,
            "row_count": row_count,
            "errors": errors,
            "preview_rows": preview_rows[:10],
            "columns": [a.tgt_field_name for a in attributes],
        }

        return render_template(
            "contracts/test_schema.html",
            contract=contract,
            entity=entity,
            sample_csv=sample_csv,
            result=result,
            config=current_app.config["APP_SETTINGS"],
        )
    finally:
        db.close()
