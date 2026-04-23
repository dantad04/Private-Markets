from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias


MYRIOTA_CANONICAL_NAME = "Myriota Pty Ltd"
MYRIOTA_SEED_SOURCE = "myriota-stage5-v1"
MYRIOTA_NOTES = (
    "Stage 5 canonical company dependency slice. Exact observed alias only from current Myriota "
    "company-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
MYRIOTA_OBSERVED_ALIASES: tuple[tuple[str, bool], ...] = (
    (MYRIOTA_CANONICAL_NAME, True),
)


def ensure_myriota_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == MYRIOTA_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="company",
            canonical_name=MYRIOTA_CANONICAL_NAME,
            notes=MYRIOTA_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_myriota_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in MYRIOTA_OBSERVED_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=MYRIOTA_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_myriota_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "company":
        raise ValueError(
            "Canonical Myriota entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'company'"
        )
    if entity.notes is None:
        entity.notes = MYRIOTA_NOTES
