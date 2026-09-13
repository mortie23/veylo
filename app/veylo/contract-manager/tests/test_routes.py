import json
from database import SessionLocal
from models.orm import Attribute, DataContract, Entity


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json == {"status": "healthy", "service": "contract-manager"}


def test_index_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Data Contracts Catalog" in res.data
    assert b"Total Contracts" in res.data


def test_create_contract(client):
    payload = {
        "contract_name": "lab-specimens",
        "contract_version": "v1.0.0",
        "data_steward_email": "steward@health.example.com.au",
        "tgt_entity_name": "lab_specimens",
        "tgt_dataset": "veylo_bronze",
        "attributes[0][src_field_name]": "Specimen ID",
        "attributes[0][tgt_field_name]": "specimen_id",
        "attributes[0][tgt_data_type]": "STRING",
        "attributes[0][is_pk]": "true",
        "attributes[0][is_nullable]": "false",
        "attributes[1][src_field_name]": "Collection Date",
        "attributes[1][tgt_field_name]": "collection_date",
        "attributes[1][tgt_data_type]": "DATE",
        "attributes[1][is_nullable]": "true",
    }

    res = client.post("/contracts", data=payload, follow_redirects=True)
    assert res.status_code == 200
    assert b"lab-specimens" in res.data
    assert b"specimen_id" in res.data

    # Verify in DB
    db = SessionLocal()
    contract = db.query(DataContract).filter_by(contract_name="lab-specimens").first()
    assert contract is not None
    assert len(contract.entities) == 1
    assert len(contract.entities[0].attributes) == 2
    db.close()


def test_toggle_contract_status(client):
    # First create a contract
    db = SessionLocal()
    c = DataContract(contract_name="test-status", contract_version="v1.0.0", is_active=True)
    db.add(c)
    db.commit()
    contract_id = c.data_contract_id
    db.close()

    res = client.post(f"/contracts/{contract_id}/toggle", follow_redirects=True)
    assert res.status_code == 200

    db = SessionLocal()
    c = db.query(DataContract).filter_by(data_contract_id=contract_id).first()
    assert c.is_active is False
    db.close()


def test_save_attribute_rules(client):
    db = SessionLocal()
    c = DataContract(contract_name="test-rules", contract_version="v1.0.0")
    db.add(c)
    db.flush()
    e = Entity(data_contract_id=c.data_contract_id, tgt_entity_name="test_entity")
    db.add(e)
    db.flush()
    a = Attribute(entity_id=e.entity_id, src_field_name="Code", tgt_field_name="code", tgt_data_type="STRING")
    db.add(a)
    db.commit()
    contract_id = c.data_contract_id
    attr_id = a.attribute_id
    db.close()

    payload = {
        "dq_rules[0][rule_type]": "REGEX",
        "dq_rules[0][rule_value]": "^[A-Z]{3}$",
        "dq_rules[0][severity]": "ERROR",
        "dq_rules[0][error_message]": "Must be 3 uppercase letters",
        "code_maps[0][code_system_name]": "TEST_CODES",
        "code_maps[0][source_code]": "ACT",
        "code_maps[0][target_code]": "ACTIVE",
        "code_maps[0][target_description]": "Active Record",
    }

    res = client.post(f"/contracts/{contract_id}/attributes/{attr_id}/rules", data=payload, follow_redirects=True)
    assert res.status_code == 200
    assert b"Validation rules and code sets updated" in res.data

    db = SessionLocal()
    a = db.query(Attribute).filter_by(attribute_id=attr_id).first()
    assert len(a.data_quality_rules) == 1
    assert a.data_quality_rules[0].rule_value == "^[A-Z]{3}$"
    assert len(a.code_management) == 1
    assert a.code_management[0].source_code == "ACT"
    db.close()


def test_schema_test_workbench(client):
    db = SessionLocal()
    c = DataContract(contract_name="test-wb", contract_version="v1.0.0")
    db.add(c)
    db.flush()
    e = Entity(data_contract_id=c.data_contract_id, tgt_entity_name="wb_test")
    db.add(e)
    db.flush()
    a1 = Attribute(entity_id=e.entity_id, src_field_name="ID", tgt_field_name="id", tgt_data_type="INT64", is_nullable=False)
    a2 = Attribute(entity_id=e.entity_id, src_field_name="Date", tgt_field_name="event_date", tgt_data_type="DATE")
    db.add_all([a1, a2])
    db.commit()
    contract_id = c.data_contract_id
    db.close()

    # Valid CSV
    valid_csv = "ID,Date\n100,2026-09-14\n101,2026-09-15"
    res = client.post(f"/contracts/{contract_id}/test", data={"sample_csv": valid_csv})
    assert res.status_code == 200
    assert b"Validation Passed!" in res.data

    # Invalid CSV (not an int, not a date)
    invalid_csv = "ID,Date\nnot_an_int,bad_date"
    res = client.post(f"/contracts/{contract_id}/test", data={"sample_csv": invalid_csv})
    assert res.status_code == 200
    assert b"Validation Failed" in res.data


def test_export_contract_json(client):
    db = SessionLocal()
    c = DataContract(contract_name="export-test", contract_version="v1.0.0")
    db.add(c)
    db.flush()
    e = Entity(data_contract_id=c.data_contract_id, tgt_entity_name="export_entity")
    db.add(e)
    db.flush()
    a = Attribute(entity_id=e.entity_id, src_field_name="Name", tgt_field_name="name", tgt_data_type="STRING")
    db.add(a)
    db.commit()
    contract_id = c.data_contract_id
    db.close()

    res = client.get(f"/api/contracts/{contract_id}/export")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["contract_name"] == "export-test"
    assert len(data["entities"]) == 1
    assert data["entities"][0]["attributes"][0]["tgt_field_name"] == "name"
