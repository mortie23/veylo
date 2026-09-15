#!/usr/bin/env python3
"""
Seed initial contract metadata into BigQuery veylo_config.
Demonstrates Step 5 in docs/DATA_VALIDATION_WAREHOUSE.md with the 'customer-returns' contract.
"""
import logging
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from services.contract_service import ContractService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed-contracts")


def seed_customer_returns():
    with SessionLocal() as db:
        existing = ContractService.get_active_contract(db, "customer-returns", "v2.1.0")
        if existing:
            logger.info("Contract 'customer-returns' (v2.1.0) already exists. Skipping.")
            return existing

        logger.info("Creating data contract 'customer-returns' (v2.1.0)...")
        contract = ContractService.create_contract(
            db=db,
            contract_name="customer-returns",
            contract_version="v2.1.0",
            data_steward_email="data-steward@veylo.internal",
            is_active=True,
        )

        entity = ContractService.add_entity(
            db=db,
            data_contract_id=contract.data_contract_id,
            src_entity_name="returns_detail",
            tgt_entity_name="returns_detail",
            tgt_dataset="veylo_bronze",
        )

        # 1. Return ID
        ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="Return ID",
            tgt_field_name="return_id",
            tgt_data_type="INT64",
            is_pk=True,
            is_nullable=False,
            ordinal_position=0,
        )

        # 2. Return Date
        ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="Return Date",
            tgt_field_name="return_date",
            tgt_data_type="DATE",
            is_nullable=False,
            ordinal_position=1,
        )

        # 3. Country Code
        country_attr = ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="Country",
            tgt_field_name="country_code",
            tgt_data_type="STRING",
            is_nullable=False,
            ordinal_position=2,
        )
        # Codes for country
        for src, tgt in [("AUS", "AU"), ("USA", "US"), ("GBR", "GB"), ("NZL", "NZ"), ("CAN", "CA")]:
            ContractService.add_code_management(
                db=db,
                attribute_id=country_attr.attribute_id,
                source_code=src,
                target_code=tgt,
                code_system_name="ISO_3166_COUNTRY",
            )

        # 4. Customer Email
        email_attr = ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="Email",
            tgt_field_name="customer_email",
            tgt_data_type="STRING",
            is_nullable=True,
            ordinal_position=3,
        )
        ContractService.add_data_quality_rule(
            db=db,
            attribute_id=email_attr.attribute_id,
            rule_type="REGEX",
            severity="ERROR",
            rule_value=r"^[^@]+@[^@]+\.[^@]+$",
            error_message_template="Field {field} value '{value}' must be a valid email address.",
        )

        # 5. Refund Amount
        amount_attr = ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="Amount",
            tgt_field_name="refund_amount",
            tgt_data_type="FLOAT64",
            is_nullable=True,
            ordinal_position=4,
        )
        ContractService.add_data_quality_rule(
            db=db,
            attribute_id=amount_attr.attribute_id,
            rule_type="RANGE",
            severity="ERROR",
            rule_value='{"min": 0, "max": 10000}',
            error_message_template="Field {field} value '{value}' must be between 0 and 10000.",
        )

        logger.info("Successfully seeded 'customer-returns' (v2.1.0) with 5 attributes and validation rules.")
        return contract


def seed_nfl_teams():
    with SessionLocal() as db:
        existing = ContractService.get_active_contract(db, "nfl-teams", "v1.0.0")
        if existing:
            logger.info("Contract 'nfl-teams' (v1.0.0) already exists. Skipping.")
            return existing

        logger.info("Creating data contract 'nfl-teams' (v1.0.0)...")
        contract = ContractService.create_contract(
            db=db,
            contract_name="nfl-teams",
            contract_version="v1.0.0",
            data_steward_email="nfl-data.steward@veylo.internal",
            is_active=True,
        )

        entity = ContractService.add_entity(
            db=db,
            data_contract_id=contract.data_contract_id,
            src_entity_name="team_lookup",
            tgt_entity_name="nfl_team_lookup",
            tgt_dataset="veylo_bronze",
        )

        # 1. TEAM_ID
        a_id = ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="TEAM_ID",
            tgt_field_name="team_id",
            tgt_data_type="INT64",
            is_pk=True,
            is_nullable=False,
            ordinal_position=0,
        )
        ContractService.add_data_quality_rule(
            db=db,
            attribute_id=a_id.attribute_id,
            rule_type="RANGE",
            severity="ERROR",
            rule_value='{"min": 1, "max": 32}',
            error_message_template="Team ID must be between 1 and 32.",
        )

        # 2. TEAM_LONG
        a_name = ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="TEAM_LONG",
            tgt_field_name="team_name",
            tgt_data_type="STRING",
            is_nullable=False,
            ordinal_position=1,
        )
        ContractService.add_data_quality_rule(
            db=db,
            attribute_id=a_name.attribute_id,
            rule_type="LENGTH",
            severity="ERROR",
            rule_value='{"min": 2, "max": 50}',
            error_message_template="Team name must be between 2 and 50 characters.",
        )

        # 3. TEAM_SHORT
        a_abbr = ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="TEAM_SHORT",
            tgt_field_name="team_abbr",
            tgt_data_type="STRING",
            is_nullable=False,
            ordinal_position=2,
        )
        ContractService.add_data_quality_rule(
            db=db,
            attribute_id=a_abbr.attribute_id,
            rule_type="REGEX",
            severity="ERROR",
            rule_value=r"^[A-Z]{2,3}$",
            error_message_template="Team abbreviation must be 2-3 uppercase letters.",
        )

        # 4. CONFERENCE
        a_conf = ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="CONFERENCE",
            tgt_field_name="conference_code",
            tgt_data_type="STRING",
            is_nullable=False,
            ordinal_position=3,
        )
        ContractService.add_data_quality_rule(
            db=db,
            attribute_id=a_conf.attribute_id,
            rule_type="ENUM",
            severity="ERROR",
            rule_value='["AFC", "NFC"]',
            error_message_template="Conference must be either AFC or NFC.",
        )
        ContractService.add_code_management(
            db=db,
            attribute_id=a_conf.attribute_id,
            source_code="AFC",
            target_code="AFC",
            code_system_name="NFL_CONFERENCE",
            target_description="American Football Conference",
        )
        ContractService.add_code_management(
            db=db,
            attribute_id=a_conf.attribute_id,
            source_code="NFC",
            target_code="NFC",
            code_system_name="NFL_CONFERENCE",
            target_description="National Football Conference",
        )

        # 5. DIVISION
        a_div = ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="DIVISION",
            tgt_field_name="division_code",
            tgt_data_type="STRING",
            is_nullable=False,
            ordinal_position=4,
        )
        for src, tgt, desc in [
            ("NFC West", "NFC_WEST", "NFC West Division"),
            ("NFC East", "NFC_EAST", "NFC East Division"),
            ("NFC South", "NFC_SOUTH", "NFC South Division"),
            ("NFC North", "NFC_NORTH", "NFC North Division"),
            ("AFC West", "AFC_WEST", "AFC West Division"),
            ("AFC East", "AFC_EAST", "AFC East Division"),
            ("AFC South", "AFC_SOUTH", "AFC South Division"),
            ("AFC North", "AFC_NORTH", "AFC North Division"),
        ]:
            ContractService.add_code_management(
                db=db,
                attribute_id=a_div.attribute_id,
                source_code=src,
                target_code=tgt,
                code_system_name="NFL_DIVISION",
                target_description=desc,
            )

        # 6. CREATE_DATE
        ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="CREATE_DATE",
            tgt_field_name="created_at",
            tgt_data_type="TIMESTAMP",
            is_nullable=True,
            ordinal_position=5,
        )

        # 7. CREATE_USER
        a_user = ContractService.add_attribute(
            db=db,
            entity_id=entity.entity_id,
            src_field_name="CREATE_USER",
            tgt_field_name="created_by",
            tgt_data_type="STRING",
            is_nullable=False,
            ordinal_position=6,
        )
        ContractService.add_data_quality_rule(
            db=db,
            attribute_id=a_user.attribute_id,
            rule_type="LENGTH",
            severity="ERROR",
            rule_value='{"min": 1, "max": 50}',
            error_message_template="Create user must not be blank.",
        )

        logger.info("Successfully seeded 'nfl-teams' (v1.0.0) with 7 attributes and validation rules.")
        return contract


if __name__ == "__main__":
    seed_customer_returns()
    seed_nfl_teams()

