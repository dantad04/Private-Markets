"""seed S2Search Australia Pty Ltd and Validly Pty Ltd canonical company entities"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Entity, EntityAlias
from app.entity_resolution.s2search_australia_seed import (
    S2SEARCH_AUSTRALIA_CANONICAL_NAME,
    ensure_s2search_australia_seed,
)
from app.entity_resolution.validly_seed import (
    VALIDLY_CANONICAL_NAME,
    ensure_validly_seed,
)


revision = "20260424_0043"
down_revision = "20260424_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        ensure_s2search_australia_seed(session)
        ensure_validly_seed(session)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        entity_ids = session.scalars(
            sa.select(Entity.id).where(
                Entity.canonical_name.in_(
                    (
                        S2SEARCH_AUSTRALIA_CANONICAL_NAME,
                        VALIDLY_CANONICAL_NAME,
                    )
                )
            )
        ).all()
        if entity_ids:
            session.execute(
                sa.delete(EntityAlias).where(EntityAlias.entity_id.in_(entity_ids))
            )
            session.execute(
                sa.delete(Entity).where(Entity.id.in_(entity_ids))
            )
        session.commit()
    finally:
        session.close()
