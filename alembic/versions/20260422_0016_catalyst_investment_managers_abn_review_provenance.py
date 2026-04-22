"""add ABR reviewed identity for Catalyst Investment Managers manager seed"""

from __future__ import annotations

from datetime import date

from alembic import op
import sqlalchemy as sa


revision = "20260422_0016"
down_revision = "20260422_0015"
branch_labels = None
depends_on = None


CATALYST_INVESTMENT_MANAGERS_CANONICAL_NAME = "Catalyst Investment Managers Pty Ltd"
CATALYST_INVESTMENT_MANAGERS_REVIEWED_ABN = "43 118 410 101"
CATALYST_INVESTMENT_MANAGERS_REVIEW_SOURCE = (
    "manual review against the Australian Business Register public record"
)
CATALYST_INVESTMENT_MANAGERS_REVIEWED_BY = "codex"
CATALYST_INVESTMENT_MANAGERS_REVIEWED_AT = "2026-04-22"
CATALYST_INVESTMENT_MANAGERS_REGISTERED_NAME_ON_ABR = "CATALYST INVESTMENT MANAGERS PTY LIMITED"
CATALYST_INVESTMENT_MANAGERS_CURRENT_LEGAL_ALIAS = "Catalyst Investment Managers Pty Limited"
CATALYST_INVESTMENT_MANAGERS_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only; no reviewed ABR or ASIC "
    "enrichment is persisted on this entity."
)
CATALYST_INVESTMENT_MANAGERS_UPDATED_NOTES = (
    "Stage 5 Catalyst Investment Managers reviewed identity proof slice. The existing canonical manager "
    "entity is enriched in place to the current ABR legal identity, with the current legal-form alias "
    "retained as a non-preferred exact-name variant."
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
            "canonical_name": CATALYST_INVESTMENT_MANAGERS_CANONICAL_NAME,
        },
    ).mappings().all()
    if len(rows) != 1:
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity expected exactly one canonical manager entity"
        )

    row = rows[0]
    if row["entity_type"] != "manager":
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity expected a manager entity, found "
            f"{row['entity_type']!r}"
        )
    if _normalise_abn(row["abn"]) not in {None, _normalise_abn(CATALYST_INVESTMENT_MANAGERS_REVIEWED_ABN)}:
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity found a conflicting ABN "
            f"({row['abn']!r})"
        )
    if row["abn_review_source"] not in {None, CATALYST_INVESTMENT_MANAGERS_REVIEW_SOURCE}:
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity found conflicting abn_review_source "
            f"({row['abn_review_source']!r})"
        )
    if row["abn_reviewed_by"] not in {None, CATALYST_INVESTMENT_MANAGERS_REVIEWED_BY}:
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity found conflicting abn_reviewed_by "
            f"({row['abn_reviewed_by']!r})"
        )
    if row["abn_reviewed_at"] not in {None, date.fromisoformat(CATALYST_INVESTMENT_MANAGERS_REVIEWED_AT)}:
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity found conflicting abn_reviewed_at "
            f"({row['abn_reviewed_at']!r})"
        )
    if row["registered_name_on_abr"] not in {None, CATALYST_INVESTMENT_MANAGERS_REGISTERED_NAME_ON_ABR}:
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity found conflicting registered_name_on_abr "
            f"({row['registered_name_on_abr']!r})"
        )
    if row["country_code"] not in {None, "", "AU"}:
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity found conflicting country_code "
            f"({row['country_code']!r})"
        )
    if row["is_australian_entity"] is False:
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity found is_australian_entity=False"
        )
    if row["confidence_tier"] not in {None, "seeded"}:
        raise RuntimeError(
            "Catalyst Investment Managers reviewed identity found conflicting confidence_tier "
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
            "abn": CATALYST_INVESTMENT_MANAGERS_REVIEWED_ABN,
            "review_source": CATALYST_INVESTMENT_MANAGERS_REVIEW_SOURCE,
            "reviewed_by": CATALYST_INVESTMENT_MANAGERS_REVIEWED_BY,
            "reviewed_at": CATALYST_INVESTMENT_MANAGERS_REVIEWED_AT,
            "registered_name_on_abr": CATALYST_INVESTMENT_MANAGERS_REGISTERED_NAME_ON_ABR,
            "is_australian_entity": True,
            "country_code": "AU",
            "confidence_tier": "seeded",
            "legacy_notes": CATALYST_INVESTMENT_MANAGERS_LEGACY_NOTES,
            "updated_notes": CATALYST_INVESTMENT_MANAGERS_UPDATED_NOTES,
            "entity_id": row["id"],
        },
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO entity_aliases (
                entity_id,
                alias,
                alias_normalized,
                source_system,
                source_file_id,
                is_preferred,
                match_confidence,
                created_at,
                updated_at
            )
            SELECT
                :entity_id,
                CAST(:alias_insert AS VARCHAR(255)),
                CAST(:alias_normalized AS VARCHAR(255)),
                CAST(:source_system AS VARCHAR(64)),
                NULL,
                :is_preferred,
                CAST(:match_confidence AS NUMERIC(6, 5)),
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1
                FROM entity_aliases
                WHERE entity_id = :entity_id
                  AND alias = CAST(:alias_lookup AS VARCHAR(255))
            )
            """
        ),
        {
            "entity_id": row["id"],
            "alias_insert": CATALYST_INVESTMENT_MANAGERS_CURRENT_LEGAL_ALIAS,
            "alias_lookup": CATALYST_INVESTMENT_MANAGERS_CURRENT_LEGAL_ALIAS,
            "alias_normalized": "catalyst investment managers pty limited",
            "source_system": "catalyst-investment-managers-stage5-v1",
            "is_preferred": False,
            "match_confidence": "1.0",
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    entity_id = bind.execute(
        sa.text("SELECT id FROM entities WHERE canonical_name = :canonical_name"),
        {"canonical_name": CATALYST_INVESTMENT_MANAGERS_CANONICAL_NAME},
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
            "updated_notes": CATALYST_INVESTMENT_MANAGERS_UPDATED_NOTES,
            "legacy_notes": CATALYST_INVESTMENT_MANAGERS_LEGACY_NOTES,
            "entity_id": entity_id,
        },
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM entity_aliases
            WHERE entity_id = :entity_id
              AND alias = CAST(:alias AS VARCHAR(255))
            """
        ),
        {
            "entity_id": entity_id,
            "alias": CATALYST_INVESTMENT_MANAGERS_CURRENT_LEGAL_ALIAS,
        },
    )


def _normalise_abn(value: str | None) -> str | None:
    if value is None:
        return None
    digits_only = "".join(character for character in value if character.isdigit())
    if len(digits_only) != 11:
        return None
    return digits_only
