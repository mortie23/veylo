import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def generate_uuid() -> str:
    return str(uuid.uuid4())


class DataContract(Base):
    __tablename__ = "data_contract"

    data_contract_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    contract_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contract_version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    data_steward_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), server_default=func.now())

    entities: Mapped[List["Entity"]] = relationship("Entity", back_populates="contract", cascade="all, delete-orphan")


class Entity(Base):
    __tablename__ = "entity"

    entity_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    data_contract_id: Mapped[str] = mapped_column(String(36), ForeignKey("data_contract.data_contract_id"), nullable=False)
    src_entity_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tgt_entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tgt_dataset: Mapped[str] = mapped_column(String(100), default="veylo_bronze", nullable=False)

    contract: Mapped["DataContract"] = relationship("DataContract", back_populates="entities")
    attributes: Mapped[List["Attribute"]] = relationship(
        "Attribute",
        back_populates="entity",
        cascade="all, delete-orphan",
        order_by="Attribute.ordinal_position",
    )


class Attribute(Base):
    __tablename__ = "attribute"

    attribute_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("entity.entity_id"), nullable=False)
    src_field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tgt_field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    src_data_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tgt_data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_pk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ordinal_position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    entity: Mapped["Entity"] = relationship("Entity", back_populates="attributes")
    code_management: Mapped[List["CodeManagement"]] = relationship(
        "CodeManagement",
        back_populates="attribute",
        cascade="all, delete-orphan",
    )
    data_quality_rules: Mapped[List["DataQuality"]] = relationship(
        "DataQuality",
        back_populates="attribute",
        cascade="all, delete-orphan",
    )


class CodeManagement(Base):
    __tablename__ = "code_management"

    code_management_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    attribute_id: Mapped[str] = mapped_column(String(36), ForeignKey("attribute.attribute_id"), nullable=False)
    code_system_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_code: Mapped[str] = mapped_column(String(255), nullable=False)
    target_code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    attribute: Mapped["Attribute"] = relationship("Attribute", back_populates="code_management")


class DataQuality(Base):
    __tablename__ = "data_quality"

    data_quality_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    attribute_id: Mapped[str] = mapped_column(String(36), ForeignKey("attribute.attribute_id"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'REGEX', 'RANGE', 'LENGTH', 'NOT_NULL', 'ENUM'
    severity: Mapped[str] = mapped_column(String(20), default="ERROR", nullable=False)  # 'ERROR', 'WARNING'
    rule_value: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    error_message_template: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    attribute: Mapped["Attribute"] = relationship("Attribute", back_populates="data_quality_rules")
