"""backfill ASIC company-register cross-reference for Myriota Pty Ltd"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Entity
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    MYRIOTA_CANONICAL_NAME,
    ensure_myriota_asic_company_register_cross_reference_subset,
)


revision = "20260423_0036"
down_revision = "20260423_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        ensure_myriota_asic_company_register_cross_reference_subset(session)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        session.execute(
            sa.update(Entity)
            .where(Entity.canonical_name == MYRIOTA_CANONICAL_NAME)
            .values(
                abn=None,
                country_code=None,
                is_australian_entity=None,
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
