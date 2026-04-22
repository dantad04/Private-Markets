from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias
from app.entity_resolution.deterministic import normalise_abn


ALPHINITY_INVESTMENT_MANAGEMENT_CANONICAL_NAME = "Alphinity Investment Management Pty Ltd"
ALPHINITY_INVESTMENT_MANAGEMENT_SEED_SOURCE = "alphinity-investment-management-stage5-v1"
ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_ABN = "12 140 833 709"
ALPHINITY_INVESTMENT_MANAGEMENT_REVIEW_SOURCE = (
    "manual review against the Australian Business Register public record"
)
ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_BY = "codex"
ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_AT = date(2026, 4, 22)
ALPHINITY_INVESTMENT_MANAGEMENT_REGISTERED_NAME_ON_ABR = "ALPHINITY INVESTMENT MANAGEMENT PTY LTD"
ALPHINITY_INVESTMENT_MANAGEMENT_HISTORICAL_NAME_ON_ABR = "Challenger Alpha Aust Shares AFSL Pty Limited"
ALPHINITY_INVESTMENT_MANAGEMENT_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only; no reviewed ABR or ASIC "
    "enrichment is persisted on this entity."
)
ALPHINITY_INVESTMENT_MANAGEMENT_NOTES = (
    "Stage 5 Alphinity Investment Management reviewed identity proof slice. The existing canonical manager "
    "entity is enriched in place to the current ABR legal identity, with the prior ABR historical name "
    "retained as a non-preferred alias."
)
ALPHINITY_INVESTMENT_MANAGEMENT_ALIASES: tuple[tuple[str, bool], ...] = (
    ("Alphinity Investment Management Pty Ltd", True),
    ("Challenger Alpha Aust Shares AFSL Pty Limited", False),
)


def ensure_alphinity_investment_management_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == ALPHINITY_INVESTMENT_MANAGEMENT_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="manager",
            canonical_name=ALPHINITY_INVESTMENT_MANAGEMENT_CANONICAL_NAME,
            abn=ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_ABN,
            abn_review_source=ALPHINITY_INVESTMENT_MANAGEMENT_REVIEW_SOURCE,
            abn_reviewed_by=ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_BY,
            abn_reviewed_at=ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_AT,
            registered_name_on_abr=ALPHINITY_INVESTMENT_MANAGEMENT_REGISTERED_NAME_ON_ABR,
            country_code="AU",
            is_australian_entity=True,
            confidence_tier="seeded",
            notes=ALPHINITY_INVESTMENT_MANAGEMENT_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_alphinity_investment_management_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in ALPHINITY_INVESTMENT_MANAGEMENT_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=ALPHINITY_INVESTMENT_MANAGEMENT_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_alphinity_investment_management_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "manager":
        raise ValueError(
            "Canonical Alphinity Investment Management entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'manager'"
        )

    if normalise_abn(entity.abn) not in {None, normalise_abn(ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_ABN)}:
        raise ValueError(
            "Canonical Alphinity Investment Management entity already has a conflicting reviewed ABN "
            f"({entity.abn!r}); expected {ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_ABN!r}"
        )
    if entity.abn is None:
        entity.abn = ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_ABN

    if entity.registered_name_on_abr not in {None, ALPHINITY_INVESTMENT_MANAGEMENT_REGISTERED_NAME_ON_ABR}:
        raise ValueError(
            "Canonical Alphinity Investment Management entity already has conflicting ABR registered-name "
            f"provenance ({entity.registered_name_on_abr!r}); expected "
            f"{ALPHINITY_INVESTMENT_MANAGEMENT_REGISTERED_NAME_ON_ABR!r}"
        )
    if entity.registered_name_on_abr is None:
        entity.registered_name_on_abr = ALPHINITY_INVESTMENT_MANAGEMENT_REGISTERED_NAME_ON_ABR

    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_review_source",
        expected_value=ALPHINITY_INVESTMENT_MANAGEMENT_REVIEW_SOURCE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_by",
        expected_value=ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_BY,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_at",
        expected_value=ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_AT,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="confidence_tier",
        expected_value="seeded",
    )

    if entity.is_australian_entity is False:
        raise ValueError(
            "Canonical Alphinity Investment Management entity is marked non-Australian despite reviewed ABR "
            "registration"
        )
    if entity.is_australian_entity is None:
        entity.is_australian_entity = True
    if entity.country_code in {None, ""}:
        entity.country_code = "AU"
    if entity.notes in {None, ALPHINITY_INVESTMENT_MANAGEMENT_LEGACY_NOTES}:
        entity.notes = ALPHINITY_INVESTMENT_MANAGEMENT_NOTES


def _ensure_matching_or_fill(entity: Entity, *, attribute_name: str, expected_value: object) -> None:
    existing_value = getattr(entity, attribute_name)
    if existing_value is None:
        setattr(entity, attribute_name, expected_value)
        return
    if existing_value != expected_value:
        raise ValueError(
            f"Canonical Alphinity Investment Management entity already has conflicting {attribute_name} "
            f"({existing_value!r}); expected {expected_value!r}"
        )
