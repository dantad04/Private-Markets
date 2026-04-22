"""add ABR reviewed identity for Wellington Management Australia manager seed"""

from __future__ import annotations

from datetime import date

from alembic import op
import sqlalchemy as sa


revision = "20260422_0014"
down_revision = "20260422_0013"
branch_labels = None
depends_on = None


WELLINGTON_MANAGEMENT_AUSTRALIA_CANONICAL_NAME = "Wellington Management Australia Pty Ltd"
WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_ABN = "19 167 091 090"
WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEW_SOURCE = (
    "manual review against the Australian Business Register public record"
)
WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_BY = "codex"
WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_AT = "2026-04-22"
WELLINGTON_MANAGEMENT_AUSTRALIA_REGISTERED_NAME_ON_ABR = "WELLINGTON MANAGEMENT AUSTRALIA PTY LTD"
WELLINGTON_MANAGEMENT_AUSTRALIA_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only; no reviewed ABR or ASIC "
    "enrichment is persisted on this entity."
)
WELLINGTON_MANAGEMENT_AUSTRALIA_UPDATED_NOTES = (
    "Stage 5 Wellington Management Australia reviewed identity proof slice. The existing canonical manager "
    "entity is enriched in place to the current ABR legal identity."
)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                entity_type,
                abn,
                abn_review_source,
                abn_reviewed_by,
                abn_reviewed_at,
                registered_name_on_abr,
                country_code,
                is_australian_entity,
                confidence_tier
            FROM entities
            WHERE canonical_name = CAST(:canonical_name AS VARCHAR(255))
            ORDER BY id ASC
            """
        ),
        {
            "canonical_name": WELLINGTON_MANAGEMENT_AUSTRALIA_CANONICAL_NAME,
        },
    ).mappings().all()
    if len(rows) != 1:
        raise RuntimeError(
            "Wellington Management Australia reviewed identity expected exactly one canonical manager entity"
        )

    row = rows[0]
    if row["entity_type"] != "manager":
        raise RuntimeError(
            "Wellington Management Australia reviewed identity expected a manager entity, found "
            f"{row['entity_type']!r}"
        )
    if _normalise_abn(row["abn"]) not in {None, _normalise_abn(WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_ABN)}:
        raise RuntimeError(
            "Wellington Management Australia reviewed identity found a conflicting ABN "
            f"({row['abn']!r})"
        )
    if row["abn_review_source"] not in {None, WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEW_SOURCE}:
        raise RuntimeError(
            "Wellington Management Australia reviewed identity found conflicting abn_review_source "
            f"({row['abn_review_source']!r})"
        )
    if row["abn_reviewed_by"] not in {None, WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_BY}:
        raise RuntimeError(
            "Wellington Management Australia reviewed identity found conflicting abn_reviewed_by "
            f"({row['abn_reviewed_by']!r})"
        )
    if row["abn_reviewed_at"] not in {None, date.fromisoformat(WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_AT)}:
        raise RuntimeError(
            "Wellington Management Australia reviewed identity found conflicting abn_reviewed_at "
            f"({row['abn_reviewed_at']!r})"
        )
    if row["registered_name_on_abr"] not in {None, WELLINGTON_MANAGEMENT_AUSTRALIA_REGISTERED_NAME_ON_ABR}:
        raise RuntimeError(
            "Wellington Management Australia reviewed identity found conflicting registered_name_on_abr "
            f"({row['registered_name_on_abr']!r})"
        )
    if row["country_code"] not in {None, "", "AU"}:
        raise RuntimeError(
            "Wellington Management Australia reviewed identity found conflicting country_code "
            f"({row['country_code']!r})"
        )
    if row["is_australian_entity"] is False:
        raise RuntimeError(
            "Wellington Management Australia reviewed identity found is_australian_entity=False"
        )
    if row["confidence_tier"] not in {None, "seeded"}:
        raise RuntimeError(
            "Wellington Management Australia reviewed identity found conflicting confidence_tier "
            f"({row['confidence_tier']!r})"
        )

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
                country_code = CASE
                    WHEN country_code IS NULL OR country_code = '' THEN CAST(:country_code AS VARCHAR(8))
                    ELSE country_code
                END,
                confidence_tier = COALESCE(confidence_tier, CAST(:confidence_tier AS VARCHAR(32))),
                notes = CASE
                    WHEN notes IS NULL OR notes = CAST(:legacy_notes AS TEXT) THEN CAST(:updated_notes AS TEXT)
                    ELSE notes
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :entity_id
            """
        ),
        {
            "abn": WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_ABN,
            "review_source": WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEW_SOURCE,
            "reviewed_by": WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_BY,
            "reviewed_at": WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_AT,
            "registered_name_on_abr": WELLINGTON_MANAGEMENT_AUSTRALIA_REGISTERED_NAME_ON_ABR,
            "is_australian_entity": True,
            "country_code": "AU",
            "confidence_tier": "seeded",
            "legacy_notes": WELLINGTON_MANAGEMENT_AUSTRALIA_LEGACY_NOTES,
            "updated_notes": WELLINGTON_MANAGEMENT_AUSTRALIA_UPDATED_NOTES,
            "entity_id": row["id"],
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    entity_id = bind.execute(
        sa.text("SELECT id FROM entities WHERE canonical_name = :canonical_name"),
        {"canonical_name": WELLINGTON_MANAGEMENT_AUSTRALIA_CANONICAL_NAME},
    ).scalar_one_or_none()
    if entity_id is None:
        return

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
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :entity_id
            """
        ),
        {
            "updated_notes": WELLINGTON_MANAGEMENT_AUSTRALIA_UPDATED_NOTES,
            "legacy_notes": WELLINGTON_MANAGEMENT_AUSTRALIA_LEGACY_NOTES,
            "entity_id": entity_id,
        },
    )


def _normalise_abn(value: str | None) -> str | None:
    if value is None:
        return None
    digits_only = "".join(character for character in value if character.isdigit())
    if len(digits_only) != 11:
        return None
    return digits_only
