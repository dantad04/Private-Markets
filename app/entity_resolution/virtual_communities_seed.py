from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias


VIRTUAL_COMMUNITIES_CANONICAL_NAME = "Virtual Communities Pty Ltd"
VIRTUAL_COMMUNITIES_SEED_SOURCE = "virtual-communities-stage5-v1"
VIRTUAL_COMMUNITIES_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only; no reviewed ABR or ASIC "
    "enrichment is persisted on this entity."
)
VIRTUAL_COMMUNITIES_OBSERVED_ALIASES: tuple[tuple[str, bool], ...] = (
    ("Virtual Communities Pty Ltd", True),
)


def ensure_virtual_communities_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == VIRTUAL_COMMUNITIES_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="manager",
            canonical_name=VIRTUAL_COMMUNITIES_CANONICAL_NAME,
            abn=None,
            country_code=None,
            is_australian_entity=None,
            confidence_tier=None,
            notes=VIRTUAL_COMMUNITIES_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_virtual_communities_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in VIRTUAL_COMMUNITIES_OBSERVED_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=VIRTUAL_COMMUNITIES_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_virtual_communities_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "manager":
        raise ValueError(
            "Canonical Virtual Communities entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'manager'"
        )

    if entity.notes is None:
        entity.notes = VIRTUAL_COMMUNITIES_NOTES
