"""seed Stafford Capital Partners canonical manager entity"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_0027"
down_revision = "20260423_0026"
branch_labels = None
depends_on = None


STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME = "Stafford Capital Partners"
STAFFORD_CAPITAL_PARTNERS_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed alias only from current Stafford "
    "manager-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
STAFFORD_CAPITAL_PARTNERS_ALIASES: tuple[tuple[str, str, bool], ...] = (
    ("Stafford Capital Partners", "stafford capital partners", True),
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO entities (
                entity_type,
                canonical_name,
                abn,
                confidence_tier,
                notes,
                created_at,
                updated_at
            )
            SELECT
                CAST(:entity_type AS VARCHAR(32)),
                CAST(:canonical_name_insert AS VARCHAR(255)),
                NULL,
                NULL,
                CAST(:notes AS TEXT),
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1
                FROM entities
                WHERE canonical_name = CAST(:canonical_name_lookup AS VARCHAR(255))
            )
            """
        ),
        {
            "entity_type": "manager",
            "canonical_name_insert": STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME,
            "canonical_name_lookup": STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME,
            "notes": STAFFORD_CAPITAL_PARTNERS_NOTES,
        },
    )

    entity_id = bind.execute(
        sa.text("SELECT id FROM entities WHERE canonical_name = :canonical_name"),
        {"canonical_name": STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME},
    ).scalar_one()

    for alias, alias_normalized, is_preferred in STAFFORD_CAPITAL_PARTNERS_ALIASES:
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
                "alias_insert": alias,
                "alias_lookup": alias,
                "alias_normalized": alias_normalized,
                "source_system": "stafford-capital-partners-stage5-v1",
                "is_preferred": is_preferred,
                "match_confidence": "1.0",
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    entity_id = bind.execute(
        sa.text("SELECT id FROM entities WHERE canonical_name = :canonical_name"),
        {"canonical_name": STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME},
    ).scalar_one_or_none()
    if entity_id is None:
        return

    bind.execute(
        sa.text("DELETE FROM entity_aliases WHERE entity_id = :entity_id"),
        {"entity_id": entity_id},
    )
    bind.execute(
        sa.text("DELETE FROM entities WHERE id = :entity_id"),
        {"entity_id": entity_id},
    )
