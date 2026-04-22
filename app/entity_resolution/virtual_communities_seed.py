from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias
from app.entity_resolution.deterministic import normalise_abn


VIRTUAL_COMMUNITIES_CANONICAL_NAME = "Virtual Communities Limited"
VIRTUAL_COMMUNITIES_LEGACY_CANONICAL_NAME = "Virtual Communities Pty Ltd"
VIRTUAL_COMMUNITIES_SEED_SOURCE = "virtual-communities-stage5-v1"
VIRTUAL_COMMUNITIES_REVIEWED_ABN = "55 086 385 346"
VIRTUAL_COMMUNITIES_REVIEW_SOURCE = "manual review against the Australian Business Register public record"
VIRTUAL_COMMUNITIES_REVIEWED_BY = "codex"
VIRTUAL_COMMUNITIES_REVIEWED_AT = date(2026, 4, 22)
VIRTUAL_COMMUNITIES_REGISTERED_NAME_ON_ABR = "VIRTUAL COMMUNITIES LIMITED"
VIRTUAL_COMMUNITIES_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only; no reviewed ABR or ASIC "
    "enrichment is persisted on this entity."
)
VIRTUAL_COMMUNITIES_NOTES = (
    "Stage 5 Virtual Communities reviewed identity-reconciliation proof slice. The canonical manager entity "
    "is reconciled in place to the current ABR-registered name, with the historical Pty Ltd observed name "
    "retained as an alias."
)
VIRTUAL_COMMUNITIES_OBSERVED_ALIASES: tuple[tuple[str, bool], ...] = (
    ("Virtual Communities Pty Ltd", True),
)


def ensure_virtual_communities_seed(session) -> Entity:
    entities = session.scalars(
        select(Entity).where(
            Entity.canonical_name.in_(
                (
                    VIRTUAL_COMMUNITIES_CANONICAL_NAME,
                    VIRTUAL_COMMUNITIES_LEGACY_CANONICAL_NAME,
                )
            )
        )
    ).all()
    unique_entity_ids = {entity.id for entity in entities}
    if len(unique_entity_ids) > 1:
        raise ValueError(
            "Virtual Communities reconciliation found multiple canonical entities across the legacy and "
            "reviewed names; expected to update one entity in place"
        )

    entity = entities[0] if entities else None
    if entity is None:
        entity = Entity(
            entity_type="manager",
            canonical_name=VIRTUAL_COMMUNITIES_CANONICAL_NAME,
            abn=VIRTUAL_COMMUNITIES_REVIEWED_ABN,
            abn_review_source=VIRTUAL_COMMUNITIES_REVIEW_SOURCE,
            abn_reviewed_by=VIRTUAL_COMMUNITIES_REVIEWED_BY,
            abn_reviewed_at=VIRTUAL_COMMUNITIES_REVIEWED_AT,
            registered_name_on_abr=VIRTUAL_COMMUNITIES_REGISTERED_NAME_ON_ABR,
            country_code="AU",
            is_australian_entity=True,
            confidence_tier="seeded",
            notes=VIRTUAL_COMMUNITIES_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_virtual_communities_seed_shape(entity)

    existing_alias_values = {
        alias_value: alias_id
        for alias_id, alias_value in session.execute(
            select(EntityAlias.id, EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
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

    if entity.canonical_name not in {
        VIRTUAL_COMMUNITIES_CANONICAL_NAME,
        VIRTUAL_COMMUNITIES_LEGACY_CANONICAL_NAME,
    }:
        raise ValueError(
            "Canonical Virtual Communities entity already exists with an unexpected canonical_name "
            f"({entity.canonical_name!r})"
        )
    if entity.canonical_name == VIRTUAL_COMMUNITIES_LEGACY_CANONICAL_NAME:
        entity.canonical_name = VIRTUAL_COMMUNITIES_CANONICAL_NAME

    if normalise_abn(entity.abn) not in {None, normalise_abn(VIRTUAL_COMMUNITIES_REVIEWED_ABN)}:
        raise ValueError(
            "Canonical Virtual Communities entity already has a conflicting reviewed ABN "
            f"({entity.abn!r}); expected {VIRTUAL_COMMUNITIES_REVIEWED_ABN!r}"
        )
    if entity.abn is None:
        entity.abn = VIRTUAL_COMMUNITIES_REVIEWED_ABN

    if entity.registered_name_on_abr not in {None, VIRTUAL_COMMUNITIES_REGISTERED_NAME_ON_ABR}:
        raise ValueError(
            "Canonical Virtual Communities entity already has conflicting ABR registered-name provenance "
            f"({entity.registered_name_on_abr!r}); expected {VIRTUAL_COMMUNITIES_REGISTERED_NAME_ON_ABR!r}"
        )
    if entity.registered_name_on_abr is None:
        entity.registered_name_on_abr = VIRTUAL_COMMUNITIES_REGISTERED_NAME_ON_ABR

    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_review_source",
        expected_value=VIRTUAL_COMMUNITIES_REVIEW_SOURCE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_by",
        expected_value=VIRTUAL_COMMUNITIES_REVIEWED_BY,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_at",
        expected_value=VIRTUAL_COMMUNITIES_REVIEWED_AT,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="confidence_tier",
        expected_value="seeded",
    )

    if entity.is_australian_entity is False:
        raise ValueError(
            "Canonical Virtual Communities entity is marked non-Australian despite reviewed ABR registration"
        )
    if entity.is_australian_entity is None:
        entity.is_australian_entity = True
    if entity.country_code in {None, ""}:
        entity.country_code = "AU"
    if entity.notes in {None, VIRTUAL_COMMUNITIES_LEGACY_NOTES}:
        entity.notes = VIRTUAL_COMMUNITIES_NOTES


def _ensure_matching_or_fill(entity: Entity, *, attribute_name: str, expected_value: object) -> None:
    existing_value = getattr(entity, attribute_name)
    if existing_value is None:
        setattr(entity, attribute_name, expected_value)
        return
    if existing_value != expected_value:
        raise ValueError(
            f"Canonical Virtual Communities entity already has conflicting {attribute_name} "
            f"({existing_value!r}); expected {expected_value!r}"
        )
