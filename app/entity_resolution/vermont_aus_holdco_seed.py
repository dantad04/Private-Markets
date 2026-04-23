from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias


VERMONT_AUS_HOLDCO_CANONICAL_NAME = "Vermont Aus Holdco Pty Ltd"
VERMONT_AUS_HOLDCO_SEED_SOURCE = "vermont-aus-holdco-stage5-v1"
VERMONT_AUS_HOLDCO_NOTES = (
    "Stage 5 canonical company dependency slice. Exact observed alias only from current Vermont Aus Holdco "
    "company-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
VERMONT_AUS_HOLDCO_OBSERVED_ALIASES: tuple[tuple[str, bool], ...] = (
    (VERMONT_AUS_HOLDCO_CANONICAL_NAME, True),
)


def ensure_vermont_aus_holdco_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == VERMONT_AUS_HOLDCO_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="company",
            canonical_name=VERMONT_AUS_HOLDCO_CANONICAL_NAME,
            notes=VERMONT_AUS_HOLDCO_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_vermont_aus_holdco_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in VERMONT_AUS_HOLDCO_OBSERVED_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=VERMONT_AUS_HOLDCO_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_vermont_aus_holdco_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "company":
        raise ValueError(
            "Canonical Vermont Aus Holdco entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'company'"
        )
    if entity.notes is None:
        entity.notes = VERMONT_AUS_HOLDCO_NOTES
