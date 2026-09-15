"""Initial veylo_config schema for data contracts

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_bigquery = bind.dialect.name == "bigquery"
    now_default = sa.text("CURRENT_DATETIME()") if is_bigquery else sa.func.current_timestamp()

    # 1. data_contract
    op.create_table(
        "data_contract",
        sa.Column("data_contract_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("contract_name", sa.String(255), nullable=False),
        sa.Column("contract_version", sa.String(50), nullable=False),
        sa.Column("data_steward_email", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=now_default, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=now_default, nullable=False),
    )
    if not is_bigquery:
        op.create_index("ix_data_contract_name", "data_contract", ["contract_name"])
        op.create_index("ix_data_contract_version", "data_contract", ["contract_version"])


    # 2. entity
    op.create_table(
        "entity",
        sa.Column("entity_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("data_contract_id", sa.String(36), sa.ForeignKey("data_contract.data_contract_id"), nullable=False),
        sa.Column("src_entity_name", sa.String(255), nullable=True),
        sa.Column("tgt_entity_name", sa.String(255), nullable=False),
        sa.Column("tgt_dataset", sa.String(100), server_default="veylo_bronze", nullable=False),
    )

    # 3. attribute
    op.create_table(
        "attribute",
        sa.Column("attribute_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entity.entity_id"), nullable=False),
        sa.Column("src_field_name", sa.String(255), nullable=False),
        sa.Column("tgt_field_name", sa.String(255), nullable=False),
        sa.Column("src_data_type", sa.String(50), nullable=True),
        sa.Column("tgt_data_type", sa.String(50), nullable=False),
        sa.Column("is_pk", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_nullable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("ordinal_position", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )

    # 4. code_management
    op.create_table(
        "code_management",
        sa.Column("code_management_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("attribute_id", sa.String(36), sa.ForeignKey("attribute.attribute_id"), nullable=False),
        sa.Column("code_system_name", sa.String(100), nullable=True),
        sa.Column("source_code", sa.String(255), nullable=False),
        sa.Column("target_code", sa.String(255), nullable=True),
        sa.Column("target_description", sa.String(500), nullable=True),
    )

    # 5. data_quality
    op.create_table(
        "data_quality",
        sa.Column("data_quality_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("attribute_id", sa.String(36), sa.ForeignKey("attribute.attribute_id"), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), server_default="ERROR", nullable=False),
        sa.Column("rule_value", sa.String(1000), nullable=True),
        sa.Column("error_message_template", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("data_quality")
    op.drop_table("code_management")
    op.drop_table("attribute")
    op.drop_table("entity")
    op.drop_table("data_contract")
