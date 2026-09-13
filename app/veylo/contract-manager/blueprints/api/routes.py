from flask import jsonify, make_response
from sqlalchemy.orm import joinedload

from blueprints.api import api_bp
from database import SessionLocal
from models.orm import Attribute, DataContract, Entity


@api_bp.route("/health")
def health_check():
    """Cloud Run health check probe."""
    return jsonify({"status": "healthy", "service": "contract-manager"}), 200


@api_bp.route("/api/contracts")
def list_contracts_api():
    """Returns JSON list of contracts."""
    db = SessionLocal()
    try:
        contracts = (
            db.query(DataContract)
            .options(joinedload(DataContract.entities).joinedload(Entity.attributes))
            .order_by(DataContract.contract_name.asc())
            .all()
        )
        return jsonify([
            {
                "data_contract_id": c.data_contract_id,
                "contract_name": c.contract_name,
                "contract_version": c.contract_version,
                "data_steward_email": c.data_steward_email,
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "entities": [
                    {
                        "entity_id": e.entity_id,
                        "tgt_entity_name": e.tgt_entity_name,
                        "src_entity_name": e.src_entity_name,
                        "tgt_dataset": e.tgt_dataset,
                        "attribute_count": len(e.attributes),
                    }
                    for e in c.entities
                ],
            }
            for c in contracts
        ])
    finally:
        db.close()


@api_bp.route("/api/contracts/<contract_id>/export")
def export_contract(contract_id: str):
    """Exports full contract definition as downloadable JSON specification."""
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
            .filter_by(data_contract_id=contract_id)
            .first()
        )

        if not contract:
            return jsonify({"error": "Contract not found"}), 404

        data = {
            "$schema": "https://veylo.io/schemas/data-contract/v1.json",
            "contract_name": contract.contract_name,
            "contract_version": contract.contract_version,
            "data_steward_email": contract.data_steward_email,
            "is_active": contract.is_active,
            "entities": [
                {
                    "src_entity_name": e.src_entity_name,
                    "tgt_entity_name": e.tgt_entity_name,
                    "tgt_dataset": e.tgt_dataset,
                    "attributes": [
                        {
                            "src_field_name": a.src_field_name,
                            "tgt_field_name": a.tgt_field_name,
                            "tgt_data_type": a.tgt_data_type,
                            "is_pk": a.is_pk,
                            "is_nullable": a.is_nullable,
                            "ordinal_position": a.ordinal_position,
                            "data_quality": [
                                {
                                    "rule_type": dq.rule_type,
                                    "severity": dq.severity,
                                    "rule_value": dq.rule_value,
                                    "error_message_template": dq.error_message_template,
                                }
                                for dq in a.data_quality_rules
                            ],
                            "code_management": [
                                {
                                    "code_system_name": cm.code_system_name,
                                    "source_code": cm.source_code,
                                    "target_code": cm.target_code,
                                    "target_description": cm.target_description,
                                }
                                for cm in a.code_management
                            ],
                        }
                        for a in e.attributes
                    ],
                }
                for e in contract.entities
            ],
        }

        resp = make_response(jsonify(data))
        resp.headers["Content-Disposition"] = f"attachment; filename=contract-{contract.contract_name}-{contract.contract_version}.json"
        return resp
    finally:
        db.close()
