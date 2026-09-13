import logging
from database import SessionLocal, init_db
from models.orm import Attribute, CodeManagement, DataContract, DataQuality, Entity

logger = logging.getLogger(__name__)


def seed_sample_contracts(force: bool = False) -> None:
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(DataContract).count()
        if existing > 0 and not force:
            logger.info(f"[Seed] Found {existing} existing contracts. Skipping seed.")
            return

        logger.info("[Seed] Seeding sample data contracts...")

        # Contract 1: Healthcare Patient Referrals (HDS aligned)
        c1 = DataContract(
            contract_name="patient-referrals",
            contract_version="v1.0.0",
            data_steward_email="data.steward@health.example.com.au",
            is_active=True,
        )
        db.add(c1)
        db.flush()

        e1 = Entity(
            data_contract_id=c1.data_contract_id,
            src_entity_name="referrals_daily",
            tgt_entity_name="patient_referrals",
            tgt_dataset="veylo_bronze",
        )
        db.add(e1)
        db.flush()

        a1_1 = Attribute(
            entity_id=e1.entity_id,
            src_field_name="Referral ID",
            tgt_field_name="referral_id",
            tgt_data_type="STRING",
            src_data_type="string",
            is_pk=True,
            is_nullable=False,
            ordinal_position=0,
        )
        db.add(a1_1)
        db.flush()
        db.add(DataQuality(
            attribute_id=a1_1.attribute_id,
            rule_type="REGEX",
            severity="ERROR",
            rule_value=r"^REF-[0-9]{6}$",
            error_message_template="Referral ID must follow format REF-XXXXXX",
        ))

        a1_2 = Attribute(
            entity_id=e1.entity_id,
            src_field_name="Referral Date",
            tgt_field_name="referral_date",
            tgt_data_type="DATE",
            src_data_type="date_iso",
            is_pk=False,
            is_nullable=False,
            ordinal_position=1,
        )
        db.add(a1_2)

        a1_3 = Attribute(
            entity_id=e1.entity_id,
            src_field_name="Priority",
            tgt_field_name="priority_code",
            tgt_data_type="STRING",
            src_data_type="string",
            is_pk=False,
            is_nullable=False,
            ordinal_position=2,
        )
        db.add(a1_3)
        db.flush()
        for src, tgt, desc in [
            ("EMERGENT", "P1", "Immediate life threat / emergency"),
            ("URGENT", "P2", "Assessment required within 30 days"),
            ("ROUTINE", "P3", "Assessment required within 90 days"),
        ]:
            db.add(CodeManagement(
                attribute_id=a1_3.attribute_id,
                code_system_name="TRIAGE_PRIORITY",
                source_code=src,
                target_code=tgt,
                target_description=desc,
            ))

        a1_4 = Attribute(
            entity_id=e1.entity_id,
            src_field_name="Patient Medicare No",
            tgt_field_name="medicare_number",
            tgt_data_type="STRING",
            src_data_type="string",
            is_pk=False,
            is_nullable=True,
            ordinal_position=3,
        )
        db.add(a1_4)
        db.flush()
        db.add(DataQuality(
            attribute_id=a1_4.attribute_id,
            rule_type="LENGTH",
            severity="ERROR",
            rule_value='{"min": 10, "max": 10}',
            error_message_template="Australian Medicare number must be exactly 10 digits",
        ))

        # Contract 2: Customer Returns (Retail)
        c2 = DataContract(
            contract_name="customer-returns",
            contract_version="v2.1.0",
            data_steward_email="ops-data@example.com",
            is_active=True,
        )
        db.add(c2)
        db.flush()

        e2 = Entity(
            data_contract_id=c2.data_contract_id,
            src_entity_name="returns_detail",
            tgt_entity_name="customer_returns",
            tgt_dataset="veylo_bronze",
        )
        db.add(e2)
        db.flush()

        a2_1 = Attribute(
            entity_id=e2.entity_id,
            src_field_name="Return ID",
            tgt_field_name="return_id",
            tgt_data_type="INT64",
            src_data_type="integer",
            is_pk=True,
            is_nullable=False,
            ordinal_position=0,
        )
        db.add(a2_1)

        a2_2 = Attribute(
            entity_id=e2.entity_id,
            src_field_name="Return Date",
            tgt_field_name="return_date",
            tgt_data_type="DATE",
            src_data_type="date_iso",
            is_pk=False,
            is_nullable=False,
            ordinal_position=1,
        )
        db.add(a2_2)

        a2_3 = Attribute(
            entity_id=e2.entity_id,
            src_field_name="Country",
            tgt_field_name="country_code",
            tgt_data_type="STRING",
            src_data_type="string",
            is_pk=False,
            is_nullable=False,
            ordinal_position=2,
        )
        db.add(a2_3)
        db.flush()
        for src, tgt in [("AUS", "AU"), ("USA", "US"), ("NZL", "NZ"), ("GBR", "GB")]:
            db.add(CodeManagement(
                attribute_id=a2_3.attribute_id,
                code_system_name="ISO_3166_COUNTRY",
                source_code=src,
                target_code=tgt,
            ))

        a2_4 = Attribute(
            entity_id=e2.entity_id,
            src_field_name="Refund Amount",
            tgt_field_name="refund_amount",
            tgt_data_type="FLOAT64",
            src_data_type="float",
            is_pk=False,
            is_nullable=True,
            ordinal_position=3,
        )
        db.add(a2_4)
        db.flush()
        db.add(DataQuality(
            attribute_id=a2_4.attribute_id,
            rule_type="RANGE",
            severity="ERROR",
            rule_value='{"min": 0, "max": 10000}',
            error_message_template="Refund amount must be between 0 and 10,000",
        ))

        db.commit()
        logger.info("[Seed] Successfully seeded 2 sample data contracts.")
    except Exception as ex:
        db.rollback()
        logger.exception(f"[Seed] Failed to seed data: {ex}")
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_sample_contracts(force=True)
