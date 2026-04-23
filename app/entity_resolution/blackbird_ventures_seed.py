from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias
from app.entity_resolution.deterministic import normalise_abn


BLACKBIRD_VENTURES_CANONICAL_NAME = "Blackbird Ventures"
BLACKBIRD_VENTURES_SEED_SOURCE = "blackbird-ventures-stage5-v1"
BLACKBIRD_VENTURES_REVIEWED_ABN = "93 159 044 989"
BLACKBIRD_VENTURES_REVIEW_SOURCE = "manual review against the Australian Business Register public record"
BLACKBIRD_VENTURES_REVIEWED_BY = "codex"
BLACKBIRD_VENTURES_REVIEWED_AT = date(2026, 4, 23)
BLACKBIRD_VENTURES_REGISTERED_NAME_ON_ABR = "BLACKBIRD VENTURES PTY LTD"
BLACKBIRD_VENTURES_OBSERVED_LEGAL_ALIAS = "Blackbird Ventures Pty Limited"
BLACKBIRD_VENTURES_CURRENT_LEGAL_ALIAS = "Blackbird Ventures Pty Ltd"
BLACKBIRD_VENTURES_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only from current Blackbird "
    "manager-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
BLACKBIRD_VENTURES_NOTES = (
    "Stage 5 Blackbird Ventures reviewed identity proof slice. The existing canonical manager entity is "
    "enriched in place to the current ABR legal identity, while preserving the current observed legal-form "
    "variant and adding the current ABR legal-form alias as non-preferred exact-name variants."
)
BLACKBIRD_VENTURES_ALIASES: tuple[tuple[str, bool], ...] = (
    (BLACKBIRD_VENTURES_CANONICAL_NAME, True),
    (BLACKBIRD_VENTURES_OBSERVED_LEGAL_ALIAS, False),
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
            abn=BLACKBIRD_VENTURES_REVIEWED_ABN,
            abn_review_source=BLACKBIRD_VENTURES_REVIEW_SOURCE,
            abn_reviewed_by=BLACKBIRD_VENTURES_REVIEWED_BY,
            abn_reviewed_at=BLACKBIRD_VENTURES_REVIEWED_AT,
            registered_name_on_abr=BLACKBIRD_VENTURES_REGISTERED_NAME_ON_ABR,
            country_code="AU",
            is_australian_entity=True,
            confidence_tier="seeded",
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

    if normalise_abn(entity.abn) not in {None, normalise_abn(BLACKBIRD_VENTURES_REVIEWED_ABN)}:
        raise ValueError(
            "Canonical Blackbird Ventures entity already has a conflicting reviewed ABN "
            f"({entity.abn!r}); expected {BLACKBIRD_VENTURES_REVIEWED_ABN!r}"
        )
    if entity.abn is None:
        entity.abn = BLACKBIRD_VENTURES_REVIEWED_ABN

    if entity.registered_name_on_abr not in {None, BLACKBIRD_VENTURES_REGISTERED_NAME_ON_ABR}:
        raise ValueError(
            "Canonical Blackbird Ventures entity already has conflicting ABR registered-name provenance "
            f"({entity.registered_name_on_abr!r}); expected {BLACKBIRD_VENTURES_REGISTERED_NAME_ON_ABR!r}"
        )
    if entity.registered_name_on_abr is None:
        entity.registered_name_on_abr = BLACKBIRD_VENTURES_REGISTERED_NAME_ON_ABR

    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_review_source",
        expected_value=BLACKBIRD_VENTURES_REVIEW_SOURCE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_by",
        expected_value=BLACKBIRD_VENTURES_REVIEWED_BY,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_at",
        expected_value=BLACKBIRD_VENTURES_REVIEWED_AT,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="confidence_tier",
        expected_value="seeded",
    )

    if entity.is_australian_entity is False:
        raise ValueError(
            "Canonical Blackbird Ventures entity is marked non-Australian despite reviewed ABR registration"
        )
    if entity.is_australian_entity is None:
        entity.is_australian_entity = True
    if entity.country_code not in {None, "", "AU"}:
        raise ValueError(
            "Canonical Blackbird Ventures entity already has a conflicting country_code "
            f"({entity.country_code!r}); expected None or 'AU'"
        )
    if entity.country_code in {None, ""}:
        entity.country_code = "AU"
    if entity.notes in {None, BLACKBIRD_VENTURES_LEGACY_NOTES}:
        entity.notes = BLACKBIRD_VENTURES_NOTES


def _ensure_matching_or_fill(entity: Entity, *, attribute_name: str, expected_value: object) -> None:
    existing_value = getattr(entity, attribute_name)
    if existing_value is None:
        setattr(entity, attribute_name, expected_value)
        return
    if existing_value != expected_value:
        raise ValueError(
            f"Canonical Blackbird Ventures entity already has conflicting {attribute_name} "
            f"({existing_value!r}); expected {expected_value!r}"
        )
