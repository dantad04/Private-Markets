from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias


S2SEARCH_AUSTRALIA_CANONICAL_NAME = "S2Search Australia Pty Ltd"
S2SEARCH_AUSTRALIA_SEED_SOURCE = "s2search-australia-stage5-v1"
S2SEARCH_AUSTRALIA_NOTES = (
    "Stage 5 canonical company dependency slice. Exact observed alias only from current S2Search Australia Pty Ltd "
    "company-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
S2SEARCH_AUSTRALIA_OBSERVED_ALIASES: tuple[tuple[str, bool], ...] = (
    (S2SEARCH_AUSTRALIA_CANONICAL_NAME, True),
)


def ensure_s2search_australia_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == S2SEARCH_AUSTRALIA_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="company",
            canonical_name=S2SEARCH_AUSTRALIA_CANONICAL_NAME,
            notes=S2SEARCH_AUSTRALIA_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_s2search_australia_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in S2SEARCH_AUSTRALIA_OBSERVED_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=S2SEARCH_AUSTRALIA_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_s2search_australia_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "company":
        raise ValueError(
            "Canonical S2Search Australia entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'company'"
        )
    if entity.notes is None:
        entity.notes = S2SEARCH_AUSTRALIA_NOTES
