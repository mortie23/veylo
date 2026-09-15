from models.orm import DataContract
from services.contract_service import ContractService


def test_contract_lifecycle(db_session):
    # 1. Create contract
    contract = ContractService.create_contract(
        db=db_session,
        contract_name="vendor-invoices",
        contract_version="v1.0.0",
        data_steward_email="finance@example.com",
    )
    assert contract.data_contract_id is not None
    assert contract.contract_name == "vendor-invoices"

    # 2. Add entity
    entity = ContractService.add_entity(
        db=db_session,
        data_contract_id=contract.data_contract_id,
        src_entity_name="invoice_headers",
        tgt_entity_name="invoice_headers",
    )
    assert entity.entity_id is not None

    # 3. Add attribute
    attr = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="Invoice Number",
        tgt_field_name="invoice_number",
        tgt_data_type="STRING",
        is_pk=True,
        is_nullable=False,
    )
    assert attr.attribute_id is not None

    # 4. Add code management
    code = ContractService.add_code_management(
        db=db_session,
        attribute_id=attr.attribute_id,
        source_code="INV",
        code_system_name="DOC_TYPE",
    )
    assert code.code_management_id is not None

    # 5. Add data quality rule
    dq = ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=attr.attribute_id,
        rule_type="LENGTH",
        rule_value='{"max": 50}',
    )
    assert dq.data_quality_id is not None

    # 6. Retrieve active contract and verify eager loading
    fetched = ContractService.get_active_contract(db_session, "vendor-invoices", "v1.0.0")
    assert fetched is not None
    assert len(fetched.entities) == 1
    assert len(fetched.entities[0].attributes) == 1
    assert len(fetched.entities[0].attributes[0].code_management) == 1
    assert len(fetched.entities[0].attributes[0].data_quality_rules) == 1


def test_get_nonexistent_contract(db_session):
    contract = ContractService.get_active_contract(db_session, "nonexistent", "v9.9.9")
    assert contract is None
