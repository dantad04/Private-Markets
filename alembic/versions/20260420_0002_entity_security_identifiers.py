"""add entity security identifiers"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_0002"
down_revision = "20260419_0001"
branch_labels = None
depends_on = None


ENTITY_IDENTIFIER_TYPE_ENUM = sa.Enum(
    "ABN",
    "ASX",
    "ISIN",
    "CUSIP",
    "LEI",
    name="entity_identifier_type",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "entity_security_identifiers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("identifier_type", ENTITY_IDENTIFIER_TYPE_ENUM, nullable=False),
        sa.Column("identifier_value", sa.String(length=128), nullable=True),
        sa.Column("is_preferred", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_entity_security_identifiers_entity_id", "entity_security_identifiers", ["entity_id"])
    op.create_index(
        "uq_entity_security_identifiers_type_value_not_null",
        "entity_security_identifiers",
        ["identifier_type", "identifier_value"],
        unique=True,
        sqlite_where=sa.text("identifier_value IS NOT NULL"),
        postgresql_where=sa.text("identifier_value IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_entity_security_identifiers_type_value_not_null", table_name="entity_security_identifiers")
    op.drop_index("ix_entity_security_identifiers_entity_id", table_name="entity_security_identifiers")
    op.drop_table("entity_security_identifiers")
