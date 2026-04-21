"""add ABN review provenance columns and backfill IFM"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_0006"
down_revision = "20260420_0005"
branch_labels = None
depends_on = None


IFM_CANONICAL_NAME = "IFM Investors Pty Ltd"
IFM_REVIEWED_ABN = "67 107 247 727"
IFM_REVIEW_SOURCE = "manual review against the Australian Business Register public record"
IFM_REVIEWED_BY = "dan"
IFM_REVIEWED_AT = "2026-04-21"
IFM_REGISTERED_NAME_ON_ABR = "IFM INVESTORS PTY LTD"
IFM_LEGACY_NOTES = (
    "Stage 3 IFM canonical worked-case seed. ABN intentionally left null in this run because it was not "
    "verified from an approved cached ASIC source."
)
IFM_UPDATED_NOTES = (
    "Stage 5 IFM canonical proof-slice seed. Reviewed ABN and ABR provenance are persisted on the "
    "canonical entity."
)


def upgrade() -> None:
    op.add_column("entities", sa.Column("abn_review_source", sa.String(length=255), nullable=True))
    op.add_column("entities", sa.Column("abn_reviewed_by", sa.String(length=255), nullable=True))
    op.add_column("entities", sa.Column("abn_reviewed_at", sa.Date(), nullable=True))
    op.add_column("entities", sa.Column("registered_name_on_abr", sa.String(length=255), nullable=True))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE entities
            SET
                abn = COALESCE(abn, CAST(:abn AS VARCHAR(32))),
                abn_review_source = COALESCE(abn_review_source, CAST(:review_source AS VARCHAR(255))),
                abn_reviewed_by = COALESCE(abn_reviewed_by, CAST(:reviewed_by AS VARCHAR(255))),
                abn_reviewed_at = COALESCE(abn_reviewed_at, CAST(:reviewed_at AS DATE)),
                registered_name_on_abr = COALESCE(
                    registered_name_on_abr,
                    CAST(:registered_name_on_abr AS VARCHAR(255))
                ),
                is_australian_entity = CASE
                    WHEN is_australian_entity IS NULL THEN :is_australian_entity
                    ELSE is_australian_entity
                END,
                country_code = COALESCE(country_code, CAST(:country_code AS VARCHAR(8))),
                notes = CASE
                    WHEN notes IS NULL OR notes = CAST(:legacy_notes AS TEXT) THEN CAST(:updated_notes AS TEXT)
                    ELSE notes
                END
            WHERE canonical_name = CAST(:canonical_name AS VARCHAR(255))
            """
        ),
        {
            "abn": IFM_REVIEWED_ABN,
            "review_source": IFM_REVIEW_SOURCE,
            "reviewed_by": IFM_REVIEWED_BY,
            "reviewed_at": IFM_REVIEWED_AT,
            "registered_name_on_abr": IFM_REGISTERED_NAME_ON_ABR,
            "is_australian_entity": True,
            "country_code": "AU",
            "legacy_notes": IFM_LEGACY_NOTES,
            "updated_notes": IFM_UPDATED_NOTES,
            "canonical_name": IFM_CANONICAL_NAME,
        },
    )


def downgrade() -> None:
    op.drop_column("entities", "registered_name_on_abr")
    op.drop_column("entities", "abn_reviewed_at")
    op.drop_column("entities", "abn_reviewed_by")
    op.drop_column("entities", "abn_review_source")
