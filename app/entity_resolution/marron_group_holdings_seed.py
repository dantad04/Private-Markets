from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias


MARRON_GROUP_HOLDINGS_CANONICAL_NAME = "Marron Group Holdings Pty Ltd"
MARRON_GROUP_HOLDINGS_SEED_SOURCE = "marron-group-holdings-stage5-v1"
MARRON_GROUP_HOLDINGS_NOTES = (
    "Stage 5 canonical company dependency slice. Exact observed alias only from current Marron Group Holdings Pty "
    "Ltd company-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
MARRON_GROUP_HOLDINGS_OBSERVED_ALIASES: tuple[tuple[str, bool], ...] = (
    (MARRON_GROUP_HOLDINGS_CANONICAL_NAME, True),
)


def ensure_marron_group_holdings_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == MARRON_GROUP_HOLDINGS_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="company",
            canonical_name=MARRON_GROUP_HOLDINGS_CANONICAL_NAME,
            notes=MARRON_GROUP_HOLDINGS_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_marron_group_holdings_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in MARRON_GROUP_HOLDINGS_OBSERVED_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=MARRON_GROUP_HOLDINGS_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_marron_group_holdings_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "company":
        raise ValueError(
            "Canonical Marron Group Holdings entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'company'"
        )
    if entity.notes is None:
        entity.notes = MARRON_GROUP_HOLDINGS_NOTES
