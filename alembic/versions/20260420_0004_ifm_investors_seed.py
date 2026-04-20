"""seed IFM Investors canonical entity"""

from __future__ import annotations

from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "20260420_0004"
down_revision = "20260420_0003"
branch_labels = None
depends_on = None


IFM_CANONICAL_NAME = "IFM Investors Pty Ltd"
IFM_NOTES = (
    "Stage 3 IFM canonical worked-case seed. ABN intentionally left null in this run because it was not "
    "verified from an approved cached ASIC source."
)
IFM_ALIASES: tuple[tuple[str, str, bool], ...] = (
    ("IFM Investors Pty Ltd", "ifm investors pty ltd", True),
    ("IFM INVESTORS PTY LIMITED", "ifm investors pty limited", False),
    ("IFM Investors", "ifm investors", False),
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
                country_code,
                is_australian_entity,
                confidence_tier,
                notes,
                created_at,
                updated_at
            )
            SELECT
                CAST(:entity_type AS VARCHAR(32)),
                CAST(:canonical_name_insert AS VARCHAR(255)),
                NULL,
                CAST(:country_code AS VARCHAR(8)),
                :is_australian_entity,
                CAST(:confidence_tier AS VARCHAR(32)),
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
            "canonical_name_insert": IFM_CANONICAL_NAME,
            "canonical_name_lookup": IFM_CANONICAL_NAME,
            "country_code": "AU",
            "is_australian_entity": True,
            "confidence_tier": "seeded",
            "notes": IFM_NOTES,
        },
    )

    entity_id = bind.execute(
        sa.text("SELECT id FROM entities WHERE canonical_name = :canonical_name"),
        {"canonical_name": IFM_CANONICAL_NAME},
    ).scalar_one()

    for alias, alias_normalized, is_preferred in IFM_ALIASES:
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
                    :match_confidence,
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
                "source_system": "ifm-stage3-v1",
                "is_preferred": is_preferred,
                "match_confidence": Decimal("1.0"),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    entity_id = bind.execute(
        sa.text("SELECT id FROM entities WHERE canonical_name = :canonical_name"),
        {"canonical_name": IFM_CANONICAL_NAME},
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
