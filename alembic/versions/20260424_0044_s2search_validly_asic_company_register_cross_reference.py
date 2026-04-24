"""backfill ASIC company-register cross-reference for S2Search Australia Pty Ltd and Validly Pty Ltd"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Entity
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    S2SEARCH_AUSTRALIA_CANONICAL_NAME,
    VALIDLY_CANONICAL_NAME,
    ensure_s2search_validly_asic_company_register_cross_reference_subset,
)


revision = "20260424_0044"
down_revision = "20260424_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        ensure_s2search_validly_asic_company_register_cross_reference_subset(session)
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
                        S2SEARCH_AUSTRALIA_CANONICAL_NAME,
                        VALIDLY_CANONICAL_NAME,
                    )
                )
            )
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
