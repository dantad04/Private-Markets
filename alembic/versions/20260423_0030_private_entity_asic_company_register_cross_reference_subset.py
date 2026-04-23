"""backfill ASIC company-register cross-reference for selected existing private entities"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Entity
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME,
    CATALYST_INVESTMENT_MANAGERS_CANONICAL_NAME,
    INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME,
    STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME,
    ensure_private_entity_asic_company_register_cross_reference_subset,
)


revision = "20260423_0030"
down_revision = "20260423_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        ensure_private_entity_asic_company_register_cross_reference_subset(session)
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
                        BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME,
                        STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME,
                        CATALYST_INVESTMENT_MANAGERS_CANONICAL_NAME,
                        INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME,
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
