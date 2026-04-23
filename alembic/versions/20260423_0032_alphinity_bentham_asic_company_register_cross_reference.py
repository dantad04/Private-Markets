"""backfill ASIC company-register cross-reference for Alphinity and Bentham"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Entity
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    ALPHINITY_INVESTMENT_MANAGEMENT_CANONICAL_NAME,
    BENTHAM_ASSET_MANAGEMENT_CANONICAL_NAME,
    ensure_alphinity_bentham_asic_company_register_cross_reference_subset,
)


revision = "20260423_0032"
down_revision = "20260423_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        ensure_alphinity_bentham_asic_company_register_cross_reference_subset(session)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        session.execute(
            sa.update(Entity)
            .where(
                Entity.canonical_name.in_(
                    (
                        ALPHINITY_INVESTMENT_MANAGEMENT_CANONICAL_NAME,
                        BENTHAM_ASSET_MANAGEMENT_CANONICAL_NAME,
                    )
                )
            )
            .values(
                acn=None,
                asic_company_status=None,
                asic_company_type=None,
                asic_registration_date=None,
                asic_next_review_date=None,
                asic_record_url=None,
                asic_review_source=None,
                asic_reviewed_by=None,
                asic_reviewed_at=None,
            )
        )
        session.commit()
    finally:
        session.close()
