"""add IFM ASIC company-register cross-reference fields and backfill IFM"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.entity_resolution.ifm_asic_company_register_cross_reference import (
    ensure_ifm_asic_company_register_cross_reference,
)


revision = "20260423_0029"
down_revision = "20260423_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entities", sa.Column("acn", sa.String(length=32), nullable=True))
    op.add_column("entities", sa.Column("asic_company_status", sa.String(length=128), nullable=True))
    op.add_column("entities", sa.Column("asic_company_type", sa.String(length=255), nullable=True))
    op.add_column("entities", sa.Column("asic_registration_date", sa.Date(), nullable=True))
    op.add_column("entities", sa.Column("asic_next_review_date", sa.Date(), nullable=True))
    op.add_column("entities", sa.Column("asic_record_url", sa.Text(), nullable=True))
    op.add_column("entities", sa.Column("asic_review_source", sa.String(length=255), nullable=True))
    op.add_column("entities", sa.Column("asic_reviewed_by", sa.String(length=255), nullable=True))
    op.add_column("entities", sa.Column("asic_reviewed_at", sa.Date(), nullable=True))

    session = Session(bind=op.get_bind())
    try:
        ensure_ifm_asic_company_register_cross_reference(session)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    op.drop_column("entities", "asic_reviewed_at")
    op.drop_column("entities", "asic_reviewed_by")
    op.drop_column("entities", "asic_review_source")
    op.drop_column("entities", "asic_record_url")
    op.drop_column("entities", "asic_next_review_date")
    op.drop_column("entities", "asic_registration_date")
    op.drop_column("entities", "asic_company_type")
    op.drop_column("entities", "asic_company_status")
    op.drop_column("entities", "acn")
