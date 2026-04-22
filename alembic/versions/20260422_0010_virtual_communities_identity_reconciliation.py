"""reconcile Virtual Communities reviewed identity"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260422_0010"
down_revision = "20260422_0009"
branch_labels = None
depends_on = None


VIRTUAL_COMMUNITIES_CANONICAL_NAME = "Virtual Communities Limited"
VIRTUAL_COMMUNITIES_LEGACY_CANONICAL_NAME = "Virtual Communities Pty Ltd"
VIRTUAL_COMMUNITIES_REVIEWED_ABN = "55 086 385 346"
VIRTUAL_COMMUNITIES_REVIEW_SOURCE = "manual review against the Australian Business Register public record"
VIRTUAL_COMMUNITIES_REVIEWED_BY = "codex"
VIRTUAL_COMMUNITIES_REVIEWED_AT = "2026-04-22"
VIRTUAL_COMMUNITIES_REGISTERED_NAME_ON_ABR = "VIRTUAL COMMUNITIES LIMITED"
VIRTUAL_COMMUNITIES_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only; no reviewed ABR or ASIC "
    "enrichment is persisted on this entity."
)
VIRTUAL_COMMUNITIES_UPDATED_NOTES = (
    "Stage 5 Virtual Communities reviewed identity-reconciliation proof slice. The canonical manager entity "
    "is reconciled in place to the current ABR-registered name, with the historical Pty Ltd observed name "
    "retained as an alias."
)


def upgrade() -> None:
    bind = op.get_bind()

    rows = bind.execute(
        sa.text(
            """
            SELECT id, canonical_name
            FROM entities
            WHERE canonical_name IN (:canonical_name, :legacy_canonical_name)
            ORDER BY id ASC
            """
        ),
        {
            "canonical_name": VIRTUAL_COMMUNITIES_CANONICAL_NAME,
            "legacy_canonical_name": VIRTUAL_COMMUNITIES_LEGACY_CANONICAL_NAME,
        },
    ).all()

    entity_ids = {row.id for row in rows}
    if len(entity_ids) > 1:
        raise RuntimeError(
            "Virtual Communities reconciliation expected one canonical entity across the legacy and reviewed names"
        )

    if rows:
        entity_id = rows[0].id
    else:
        entity_id = bind.execute(
            sa.text(
                """
                INSERT INTO entities (
                    entity_type,
                    canonical_name,
                    abn,
                    abn_review_source,
                    abn_reviewed_by,
                    abn_reviewed_at,
                    registered_name_on_abr,
                    country_code,
                    is_australian_entity,
                    confidence_tier,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (
                    CAST(:entity_type AS VARCHAR(32)),
                    CAST(:canonical_name AS VARCHAR(255)),
                    CAST(:abn AS VARCHAR(32)),
                    CAST(:review_source AS VARCHAR(255)),
                    CAST(:reviewed_by AS VARCHAR(255)),
                    CAST(:reviewed_at AS DATE),
                    CAST(:registered_name_on_abr AS VARCHAR(255)),
                    CAST(:country_code AS VARCHAR(8)),
                    :is_australian_entity,
                    CAST(:confidence_tier AS VARCHAR(32)),
                    CAST(:notes AS TEXT),
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                RETURNING id
                """
            ),
            {
                "entity_type": "manager",
                "canonical_name": VIRTUAL_COMMUNITIES_CANONICAL_NAME,
                "abn": VIRTUAL_COMMUNITIES_REVIEWED_ABN,
                "review_source": VIRTUAL_COMMUNITIES_REVIEW_SOURCE,
                "reviewed_by": VIRTUAL_COMMUNITIES_REVIEWED_BY,
                "reviewed_at": VIRTUAL_COMMUNITIES_REVIEWED_AT,
                "registered_name_on_abr": VIRTUAL_COMMUNITIES_REGISTERED_NAME_ON_ABR,
                "country_code": "AU",
                "is_australian_entity": True,
                "confidence_tier": "seeded",
                "notes": VIRTUAL_COMMUNITIES_UPDATED_NOTES,
            },
        ).scalar_one()

    bind.execute(
        sa.text(
            """
            UPDATE entities
            SET canonical_name = CAST(:canonical_name AS VARCHAR(255)),
                abn = CAST(:abn AS VARCHAR(32)),
                abn_review_source = CAST(:review_source AS VARCHAR(255)),
                abn_reviewed_by = CAST(:reviewed_by AS VARCHAR(255)),
                abn_reviewed_at = CAST(:reviewed_at AS DATE),
                registered_name_on_abr = CAST(:registered_name_on_abr AS VARCHAR(255)),
                country_code = CAST(:country_code AS VARCHAR(8)),
                is_australian_entity = :is_australian_entity,
                confidence_tier = CAST(:confidence_tier AS VARCHAR(32)),
                notes = CASE
                    WHEN notes IS NULL OR notes = CAST(:legacy_notes AS TEXT)
                    THEN CAST(:updated_notes AS TEXT)
                    ELSE notes
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :entity_id
            """
        ),
        {
            "canonical_name": VIRTUAL_COMMUNITIES_CANONICAL_NAME,
            "abn": VIRTUAL_COMMUNITIES_REVIEWED_ABN,
            "review_source": VIRTUAL_COMMUNITIES_REVIEW_SOURCE,
            "reviewed_by": VIRTUAL_COMMUNITIES_REVIEWED_BY,
            "reviewed_at": VIRTUAL_COMMUNITIES_REVIEWED_AT,
            "registered_name_on_abr": VIRTUAL_COMMUNITIES_REGISTERED_NAME_ON_ABR,
            "country_code": "AU",
            "is_australian_entity": True,
            "confidence_tier": "seeded",
            "legacy_notes": VIRTUAL_COMMUNITIES_LEGACY_NOTES,
            "updated_notes": VIRTUAL_COMMUNITIES_UPDATED_NOTES,
            "entity_id": entity_id,
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
            "entity_id": entity_id,
            "alias_insert": VIRTUAL_COMMUNITIES_LEGACY_CANONICAL_NAME,
            "alias_lookup": VIRTUAL_COMMUNITIES_LEGACY_CANONICAL_NAME,
            "alias_normalized": "virtual communities pty ltd",
            "source_system": "virtual-communities-stage5-v1",
            "is_preferred": True,
            "match_confidence": "1.0",
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    entity_id = bind.execute(
        sa.text("SELECT id FROM entities WHERE canonical_name = :canonical_name"),
        {"canonical_name": VIRTUAL_COMMUNITIES_CANONICAL_NAME},
    ).scalar_one_or_none()
    if entity_id is None:
        return

    bind.execute(
        sa.text(
            """
            UPDATE entities
            SET canonical_name = CAST(:legacy_canonical_name AS VARCHAR(255)),
                abn = NULL,
                abn_review_source = NULL,
                abn_reviewed_by = NULL,
                abn_reviewed_at = NULL,
                registered_name_on_abr = NULL,
                country_code = NULL,
                is_australian_entity = NULL,
                confidence_tier = NULL,
                notes = CAST(:legacy_notes AS TEXT),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :entity_id
            """
        ),
        {
            "legacy_canonical_name": VIRTUAL_COMMUNITIES_LEGACY_CANONICAL_NAME,
            "legacy_notes": VIRTUAL_COMMUNITIES_LEGACY_NOTES,
            "entity_id": entity_id,
        },
    )
