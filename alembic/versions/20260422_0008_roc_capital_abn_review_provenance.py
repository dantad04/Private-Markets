"""add ABN review provenance for ROC Capital manager seed"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260422_0008"
down_revision = "20260422_0007"
branch_labels = None
depends_on = None


ROC_CAPITAL_CANONICAL_NAME = "ROC Capital Pty Limited"
ROC_CAPITAL_REVIEWED_ABN = "37 167 858 764"
ROC_CAPITAL_REVIEW_SOURCE = "manual review against the Australian Business Register public record"
ROC_CAPITAL_REVIEWED_BY = "codex"
ROC_CAPITAL_REVIEWED_AT = "2026-04-22"
ROC_CAPITAL_REGISTERED_NAME_ON_ABR = "ROC CAPITAL PTY LIMITED"
ROC_CAPITAL_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only; no reviewed ABR or ASIC "
    "enrichment is persisted on this entity."
)
ROC_CAPITAL_UPDATED_NOTES = (
    "Stage 5 ROC Capital proof-slice seed. Reviewed ABN and ABR provenance are persisted on the canonical "
    "manager entity."
)


def upgrade() -> None:
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
                confidence_tier = COALESCE(confidence_tier, CAST(:confidence_tier AS VARCHAR(32))),
                notes = CASE
                    WHEN notes IS NULL OR notes = CAST(:legacy_notes AS TEXT) THEN CAST(:updated_notes AS TEXT)
                    ELSE notes
                END
            WHERE canonical_name = CAST(:canonical_name AS VARCHAR(255))
            """
        ),
        {
            "abn": ROC_CAPITAL_REVIEWED_ABN,
            "review_source": ROC_CAPITAL_REVIEW_SOURCE,
            "reviewed_by": ROC_CAPITAL_REVIEWED_BY,
            "reviewed_at": ROC_CAPITAL_REVIEWED_AT,
            "registered_name_on_abr": ROC_CAPITAL_REGISTERED_NAME_ON_ABR,
            "is_australian_entity": True,
            "country_code": "AU",
            "confidence_tier": "seeded",
            "legacy_notes": ROC_CAPITAL_LEGACY_NOTES,
            "updated_notes": ROC_CAPITAL_UPDATED_NOTES,
            "canonical_name": ROC_CAPITAL_CANONICAL_NAME,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE entities
            SET
                abn = NULL,
                abn_review_source = NULL,
                abn_reviewed_by = NULL,
                abn_reviewed_at = NULL,
                registered_name_on_abr = NULL,
                is_australian_entity = NULL,
                country_code = NULL,
                confidence_tier = NULL,
                notes = CASE
                    WHEN notes = CAST(:updated_notes AS TEXT) THEN CAST(:legacy_notes AS TEXT)
                    ELSE notes
                END
            WHERE canonical_name = CAST(:canonical_name AS VARCHAR(255))
            """
        ),
        {
            "updated_notes": ROC_CAPITAL_UPDATED_NOTES,
            "legacy_notes": ROC_CAPITAL_LEGACY_NOTES,
            "canonical_name": ROC_CAPITAL_CANONICAL_NAME,
        },
    )
