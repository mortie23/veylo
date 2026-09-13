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
from sqlalchemy.orm import joinedload

from blueprints.rules import rules_bp
from database import SessionLocal
from models.orm import Attribute, CodeManagement, DataContract, DataQuality


@rules_bp.route("/contracts/<contract_id>/attributes/<attribute_id>/rules", methods=["GET"])
def edit_attribute_rules(contract_id: str, attribute_id: str):
    """Renders the DQ rules and Code sets designer for a specific attribute."""
    db = SessionLocal()
    try:
        contract = db.query(DataContract).filter_by(data_contract_id=contract_id).first()
        attribute = (
            db.query(Attribute)
            .options(
                joinedload(Attribute.data_quality_rules),
                joinedload(Attribute.code_management),
            )
            .filter_by(attribute_id=attribute_id)
            .first()
        )

        if not contract or not attribute:
            flash("Attribute or contract not found.", "danger")
            return redirect(url_for("contracts.index"))

        return render_template(
            "rules/edit_attribute.html",
            contract=contract,
            attribute=attribute,
            config=current_app.config["APP_SETTINGS"],
        )
    finally:
        db.close()


@rules_bp.route("/contracts/<contract_id>/attributes/<attribute_id>/rules", methods=["POST"])
def save_attribute_rules(contract_id: str, attribute_id: str):
    """Saves updated DQ rules and Code sets for the attribute."""
    form = request.form
    db = SessionLocal()
    try:
        attribute = db.query(Attribute).filter_by(attribute_id=attribute_id).first()
        contract = db.query(DataContract).filter_by(data_contract_id=contract_id).first()

        if not attribute or not contract:
            flash("Attribute or contract not found.", "danger")
            return redirect(url_for("contracts.index"))

        # Clear existing rules and code sets for this attribute
        db.query(DataQuality).filter_by(attribute_id=attribute_id).delete()
        db.query(CodeManagement).filter_by(attribute_id=attribute_id).delete()

        # Parse new DQ rules from form
        dq_dict = {}
        for key, value in form.items():
            match = re.match(r"dq_rules\[(\d+)\]\[(\w+)\]", key)
            if match:
                idx, field = match.groups()
                idx = int(idx)
                if idx not in dq_dict:
                    dq_dict[idx] = {}
                dq_dict[idx][field] = value.strip()

        for idx in sorted(dq_dict.keys()):
            item = dq_dict[idx]
            rule_type = item.get("rule_type")
            rule_value = item.get("rule_value") or None
            severity = item.get("severity", "ERROR")
            err_msg = item.get("error_message") or None

            if rule_type:
                db.add(DataQuality(
                    attribute_id=attribute.attribute_id,
                    rule_type=rule_type,
                    rule_value=rule_value,
                    severity=severity,
                    error_message_template=err_msg,
                ))

        # Parse new Code Management entries from form
        code_dict = {}
        for key, value in form.items():
            match = re.match(r"code_maps\[(\d+)\]\[(\w+)\]", key)
            if match:
                idx, field = match.groups()
                idx = int(idx)
                if idx not in code_dict:
                    code_dict[idx] = {}
                code_dict[idx][field] = value.strip()

        for idx in sorted(code_dict.keys()):
            item = code_dict[idx]
            source_code = item.get("source_code")
            target_code = item.get("target_code") or None
            code_system = item.get("code_system_name") or None
            desc = item.get("target_description") or None

            if source_code:
                db.add(CodeManagement(
                    attribute_id=attribute.attribute_id,
                    code_system_name=code_system,
                    source_code=source_code,
                    target_code=target_code,
                    target_description=desc,
                ))

        contract.updated_at = datetime.now(timezone.utc)
        db.commit()
        flash(f"Validation rules and code sets updated for '{attribute.tgt_field_name}'.", "success")
        return redirect(url_for("contracts.detail", contract_id=contract_id))
    except Exception as ex:
        db.rollback()
        flash(f"Failed to save rules: {ex}", "danger")
        return redirect(url_for("rules.edit_attribute_rules", contract_id=contract_id, attribute_id=attribute_id))
    finally:
        db.close()
