"""add entity match overrides"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_0005"
down_revision = "20260420_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_match_overrides",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("raw_name_normalized", sa.String(length=255), nullable=False),
        sa.Column("entity_type_scope", sa.String(length=32), nullable=True),
        sa.Column("source_fund_id", sa.Integer(), sa.ForeignKey("funds.id"), nullable=True),
        sa.Column("source_asset_class_scope", sa.String(length=255), nullable=True),
        sa.Column("matched_entity_id", sa.Integer(), sa.ForeignKey("entities.id"), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action IN ('force_match', 'force_no_match', 'force_new_entity', 'redirect_to_parent')",
            name="ck_entity_match_overrides_action",
        ),
    )
    op.create_index(
        "ix_entity_match_overrides_raw_name_normalized",
        "entity_match_overrides",
        ["raw_name_normalized"],
    )
    op.create_index("ix_entity_match_overrides_source_fund_id", "entity_match_overrides", ["source_fund_id"])


def downgrade() -> None:
    op.drop_index("ix_entity_match_overrides_source_fund_id", table_name="entity_match_overrides")
    op.drop_index("ix_entity_match_overrides_raw_name_normalized", table_name="entity_match_overrides")
    op.drop_table("entity_match_overrides")
