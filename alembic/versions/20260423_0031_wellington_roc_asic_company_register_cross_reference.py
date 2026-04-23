"""backfill ASIC company-register cross-reference for Wellington and ROC"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Entity
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    ROC_CAPITAL_CANONICAL_NAME,
    WELLINGTON_MANAGEMENT_AUSTRALIA_CANONICAL_NAME,
    ensure_wellington_roc_asic_company_register_cross_reference_subset,
)


revision = "20260423_0031"
down_revision = "20260423_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        ensure_wellington_roc_asic_company_register_cross_reference_subset(session)
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
                        WELLINGTON_MANAGEMENT_AUSTRALIA_CANONICAL_NAME,
                        ROC_CAPITAL_CANONICAL_NAME,
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
