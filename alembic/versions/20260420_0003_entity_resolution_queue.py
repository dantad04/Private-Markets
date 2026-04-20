"""add entity resolution queue"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_0003"
down_revision = "20260420_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_resolution_queue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("holding_id", sa.Integer(), sa.ForeignKey("holdings.id"), nullable=False),
        sa.Column("candidate_entity_ids", sa.JSON(), nullable=False),
        sa.Column("top_candidate_score", sa.Numeric(6, 5), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_entity_resolution_queue_holding_id", "entity_resolution_queue", ["holding_id"])


def downgrade() -> None:
    op.drop_index("ix_entity_resolution_queue_holding_id", table_name="entity_resolution_queue")
    op.drop_table("entity_resolution_queue")
