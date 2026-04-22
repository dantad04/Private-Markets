from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias


BLACKBIRD_VENTURES_CANONICAL_NAME = "Blackbird Ventures"
BLACKBIRD_VENTURES_SEED_SOURCE = "blackbird-ventures-stage5-v1"
BLACKBIRD_VENTURES_CURRENT_LEGAL_ALIAS = "Blackbird Ventures Pty Limited"
BLACKBIRD_VENTURES_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only from current Blackbird "
    "manager-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
BLACKBIRD_VENTURES_ALIASES: tuple[tuple[str, bool], ...] = (
    (BLACKBIRD_VENTURES_CANONICAL_NAME, True),
    (BLACKBIRD_VENTURES_CURRENT_LEGAL_ALIAS, False),
)


def ensure_blackbird_ventures_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == BLACKBIRD_VENTURES_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="manager",
            canonical_name=BLACKBIRD_VENTURES_CANONICAL_NAME,
            notes=BLACKBIRD_VENTURES_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_blackbird_ventures_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in BLACKBIRD_VENTURES_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=BLACKBIRD_VENTURES_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_blackbird_ventures_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "manager":
        raise ValueError(
            "Canonical Blackbird Ventures entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'manager'"
        )
    if entity.notes is None:
        entity.notes = BLACKBIRD_VENTURES_NOTES
