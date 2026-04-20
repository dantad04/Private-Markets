from __future__ import annotations

from decimal import Decimal

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias


IFM_CANONICAL_NAME = "IFM Investors Pty Ltd"
IFM_OBSERVED_ALIASES: tuple[tuple[str, bool], ...] = (
    ("IFM Investors Pty Ltd", True),
    ("IFM INVESTORS PTY LIMITED", False),
    ("IFM Investors", False),
)


def ensure_ifm_seed(session) -> Entity:
    entity = session.query(Entity).filter(Entity.canonical_name == IFM_CANONICAL_NAME).one_or_none()
    if entity is None:
        entity = Entity(
            entity_type="manager",
            canonical_name=IFM_CANONICAL_NAME,
            abn=None,
            country_code="AU",
            is_australian_entity=True,
            confidence_tier="seeded",
            notes=(
                "Stage 3 IFM canonical worked-case seed. ABN intentionally left null in this run "
                "because it was not verified from an approved cached ASIC source."
            ),
        )
        session.add(entity)
        session.flush()

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.query(EntityAlias.alias).filter(EntityAlias.entity_id == entity.id).all()
    }

    for alias, is_preferred in IFM_OBSERVED_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system="ifm-stage3-v1",
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )
    session.flush()
    return entity
