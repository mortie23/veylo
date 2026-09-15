import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.orm import Attribute, CodeManagement, DataContract, DataQuality, Entity

logger = logging.getLogger(__name__)


class ContractService:
    """Service to query and manage data contracts in BigQuery veylo_config."""

    @staticmethod
    def get_active_contract(
        db: Session,
        contract_name: str,
        contract_version: str
    ) -> Optional[DataContract]:
        """
        Retrieves an active data contract by name and version with all associated
        entities, attributes, code management sets, and data quality rules eagerly loaded.
        """
        stmt = (
            select(DataContract)
            .where(
                DataContract.contract_name == contract_name,
                DataContract.contract_version == contract_version,
                DataContract.is_active.is_(True),
            )
            .options(
                selectinload(DataContract.entities)
                .selectinload(Entity.attributes)
                .selectinload(Attribute.code_management),
                selectinload(DataContract.entities)
                .selectinload(Entity.attributes)
                .selectinload(Attribute.data_quality_rules),
            )
        )
        result = db.execute(stmt).scalars().first()
        return result

    @staticmethod
    def list_contracts(
        db: Session,
        active_only: bool = False
    ) -> List[DataContract]:
        """Lists data contracts."""
        stmt = select(DataContract)
        if active_only:
            stmt = stmt.where(DataContract.is_active.is_(True))
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def create_contract(
        db: Session,
        contract_name: str,
        contract_version: str,
        data_steward_email: Optional[str] = None,
        is_active: bool = True,
    ) -> DataContract:
        """Creates a new data contract header."""
        contract = DataContract(
            contract_name=contract_name,
            contract_version=contract_version,
            data_steward_email=data_steward_email,
            is_active=is_active,
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)
        return contract

    @staticmethod
    def add_entity(
        db: Session,
        data_contract_id: str,
        tgt_entity_name: str,
        src_entity_name: Optional[str] = None,
        tgt_dataset: str = "veylo_bronze",
    ) -> Entity:
        """Adds an entity/table to a data contract."""
        entity = Entity(
            data_contract_id=data_contract_id,
            src_entity_name=src_entity_name,
            tgt_entity_name=tgt_entity_name,
            tgt_dataset=tgt_dataset,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return entity

    @staticmethod
    def add_attribute(
        db: Session,
        entity_id: str,
        src_field_name: str,
        tgt_field_name: str,
        tgt_data_type: str,
        src_data_type: Optional[str] = None,
        is_pk: bool = False,
        is_nullable: bool = True,
        ordinal_position: int = 0,
    ) -> Attribute:
        """Adds an attribute column definition to an entity."""
        attribute = Attribute(
            entity_id=entity_id,
            src_field_name=src_field_name,
            tgt_field_name=tgt_field_name,
            tgt_data_type=tgt_data_type.upper(),
            src_data_type=src_data_type,
            is_pk=is_pk,
            is_nullable=is_nullable,
            ordinal_position=ordinal_position,
        )
        db.add(attribute)
        db.commit()
        db.refresh(attribute)
        return attribute

    @staticmethod
    def add_code_management(
        db: Session,
        attribute_id: str,
        source_code: str,
        code_system_name: Optional[str] = None,
        target_code: Optional[str] = None,
        target_description: Optional[str] = None,
    ) -> CodeManagement:
        """Adds an allowed code value mapping to an attribute."""
        code = CodeManagement(
            attribute_id=attribute_id,
            code_system_name=code_system_name,
            source_code=source_code,
            target_code=target_code or source_code,
            target_description=target_description,
        )
        db.add(code)
        db.commit()
        db.refresh(code)
        return code

    @staticmethod
    def add_data_quality_rule(
        db: Session,
        attribute_id: str,
        rule_type: str,
        severity: str = "ERROR",
        rule_value: Optional[str] = None,
        error_message_template: Optional[str] = None,
    ) -> DataQuality:
        """Adds a data quality rule constraint to an attribute."""
        rule = DataQuality(
            attribute_id=attribute_id,
            rule_type=rule_type.upper(),
            severity=severity.upper(),
            rule_value=rule_value,
            error_message_template=error_message_template,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule
