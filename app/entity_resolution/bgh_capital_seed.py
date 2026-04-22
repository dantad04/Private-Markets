from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias
from app.entity_resolution.deterministic import normalise_abn


BGH_CAPITAL_CANONICAL_NAME = "BGH Capital"
BGH_CAPITAL_SEED_SOURCE = "bgh-capital-stage5-v1"
BGH_CAPITAL_REVIEWED_ABN = "59 617 386 982"
BGH_CAPITAL_REVIEW_SOURCE = "manual review against the Australian Business Register public record"
BGH_CAPITAL_REVIEWED_BY = "codex"
BGH_CAPITAL_REVIEWED_AT = date(2026, 4, 22)
BGH_CAPITAL_REGISTERED_NAME_ON_ABR = "BGH CAPITAL PTY LTD"
BGH_CAPITAL_CURRENT_LEGAL_ALIAS = "BGH Capital Pty Ltd"
BGH_CAPITAL_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed alias only from current BGH "
    "manager-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
BGH_CAPITAL_NOTES = (
    "Stage 5 BGH Capital reviewed identity proof slice. The existing canonical manager entity is "
    "enriched in place to the current ABR legal identity, with the current legal-form alias retained "
    "as a non-preferred exact-name variant."
)
BGH_CAPITAL_ALIASES: tuple[tuple[str, bool], ...] = (
    (BGH_CAPITAL_CANONICAL_NAME, True),
    (BGH_CAPITAL_CURRENT_LEGAL_ALIAS, False),
)


def ensure_bgh_capital_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == BGH_CAPITAL_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="manager",
            canonical_name=BGH_CAPITAL_CANONICAL_NAME,
            abn=BGH_CAPITAL_REVIEWED_ABN,
            abn_review_source=BGH_CAPITAL_REVIEW_SOURCE,
            abn_reviewed_by=BGH_CAPITAL_REVIEWED_BY,
            abn_reviewed_at=BGH_CAPITAL_REVIEWED_AT,
            registered_name_on_abr=BGH_CAPITAL_REGISTERED_NAME_ON_ABR,
            country_code="AU",
            is_australian_entity=True,
            confidence_tier="seeded",
            notes=BGH_CAPITAL_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_bgh_capital_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in BGH_CAPITAL_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=BGH_CAPITAL_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_bgh_capital_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "manager":
        raise ValueError(
            "Canonical BGH Capital entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'manager'"
        )

    if normalise_abn(entity.abn) not in {None, normalise_abn(BGH_CAPITAL_REVIEWED_ABN)}:
        raise ValueError(
            "Canonical BGH Capital entity already has a conflicting reviewed ABN "
            f"({entity.abn!r}); expected {BGH_CAPITAL_REVIEWED_ABN!r}"
        )
    if entity.abn is None:
        entity.abn = BGH_CAPITAL_REVIEWED_ABN

    if entity.registered_name_on_abr not in {None, BGH_CAPITAL_REGISTERED_NAME_ON_ABR}:
        raise ValueError(
            "Canonical BGH Capital entity already has conflicting ABR registered-name provenance "
            f"({entity.registered_name_on_abr!r}); expected {BGH_CAPITAL_REGISTERED_NAME_ON_ABR!r}"
        )
    if entity.registered_name_on_abr is None:
        entity.registered_name_on_abr = BGH_CAPITAL_REGISTERED_NAME_ON_ABR

    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_review_source",
        expected_value=BGH_CAPITAL_REVIEW_SOURCE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_by",
        expected_value=BGH_CAPITAL_REVIEWED_BY,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_at",
        expected_value=BGH_CAPITAL_REVIEWED_AT,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="confidence_tier",
        expected_value="seeded",
    )

    if entity.is_australian_entity is False:
        raise ValueError(
            "Canonical BGH Capital entity is marked non-Australian despite reviewed ABR registration"
        )
    if entity.is_australian_entity is None:
        entity.is_australian_entity = True
    if entity.country_code in {None, ""}:
        entity.country_code = "AU"
    if entity.notes in {None, BGH_CAPITAL_LEGACY_NOTES}:
        entity.notes = BGH_CAPITAL_NOTES


def _ensure_matching_or_fill(entity: Entity, *, attribute_name: str, expected_value: object) -> None:
    existing_value = getattr(entity, attribute_name)
    if existing_value is None:
        setattr(entity, attribute_name, expected_value)
        return
    if existing_value != expected_value:
        raise ValueError(
            f"Canonical BGH Capital entity already has conflicting {attribute_name} "
            f"({existing_value!r}); expected {expected_value!r}"
        )
