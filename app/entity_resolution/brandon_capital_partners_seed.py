from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias
from app.entity_resolution.deterministic import normalise_abn


BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME = "Brandon Capital Partners"
BRANDON_CAPITAL_PARTNERS_SEED_SOURCE = "brandon-capital-partners-stage5-v1"
BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN = "82 128 415 903"
BRANDON_CAPITAL_PARTNERS_REVIEW_SOURCE = (
    "manual review against the Australian Business Register public record"
)
BRANDON_CAPITAL_PARTNERS_REVIEWED_BY = "codex"
BRANDON_CAPITAL_PARTNERS_REVIEWED_AT = date(2026, 4, 22)
BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR = "BRANDON CAPITAL PARTNERS PTY LTD"
BRANDON_CAPITAL_PARTNERS_CURRENT_LEGAL_ALIAS = "Brandon Capital Partners Pty Ltd"
BRANDON_CAPITAL_PARTNERS_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed alias only from current Brandon "
    "manager-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
BRANDON_CAPITAL_PARTNERS_NOTES = (
    "Stage 5 Brandon Capital Partners reviewed identity proof slice. The existing canonical manager "
    "entity is enriched in place to the current ABR legal identity, with the current legal-form alias "
    "retained as a non-preferred exact-name variant."
)
BRANDON_CAPITAL_PARTNERS_ALIASES: tuple[tuple[str, bool], ...] = (
    ("Brandon Capital Partners", True),
    (BRANDON_CAPITAL_PARTNERS_CURRENT_LEGAL_ALIAS, False),
)


def ensure_brandon_capital_partners_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="manager",
            canonical_name=BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME,
            abn=BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN,
            abn_review_source=BRANDON_CAPITAL_PARTNERS_REVIEW_SOURCE,
            abn_reviewed_by=BRANDON_CAPITAL_PARTNERS_REVIEWED_BY,
            abn_reviewed_at=BRANDON_CAPITAL_PARTNERS_REVIEWED_AT,
            registered_name_on_abr=BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR,
            country_code="AU",
            is_australian_entity=True,
            confidence_tier="seeded",
            notes=BRANDON_CAPITAL_PARTNERS_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_brandon_capital_partners_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in BRANDON_CAPITAL_PARTNERS_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=BRANDON_CAPITAL_PARTNERS_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_brandon_capital_partners_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "manager":
        raise ValueError(
            "Canonical Brandon Capital Partners entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'manager'"
        )

    if normalise_abn(entity.abn) not in {None, normalise_abn(BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN)}:
        raise ValueError(
            "Canonical Brandon Capital Partners entity already has a conflicting reviewed ABN "
            f"({entity.abn!r}); expected {BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN!r}"
        )
    if entity.abn is None:
        entity.abn = BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN

    if entity.registered_name_on_abr not in {None, BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR}:
        raise ValueError(
            "Canonical Brandon Capital Partners entity already has conflicting ABR registered-name "
            f"provenance ({entity.registered_name_on_abr!r}); expected "
            f"{BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR!r}"
        )
    if entity.registered_name_on_abr is None:
        entity.registered_name_on_abr = BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR

    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_review_source",
        expected_value=BRANDON_CAPITAL_PARTNERS_REVIEW_SOURCE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_by",
        expected_value=BRANDON_CAPITAL_PARTNERS_REVIEWED_BY,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_at",
        expected_value=BRANDON_CAPITAL_PARTNERS_REVIEWED_AT,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="confidence_tier",
        expected_value="seeded",
    )

    if entity.is_australian_entity is False:
        raise ValueError(
            "Canonical Brandon Capital Partners entity is marked non-Australian despite reviewed ABR "
            "registration"
        )
    if entity.is_australian_entity is None:
        entity.is_australian_entity = True
    if entity.country_code in {None, ""}:
        entity.country_code = "AU"
    if entity.notes in {None, BRANDON_CAPITAL_PARTNERS_LEGACY_NOTES}:
        entity.notes = BRANDON_CAPITAL_PARTNERS_NOTES


def _ensure_matching_or_fill(entity: Entity, *, attribute_name: str, expected_value: object) -> None:
    existing_value = getattr(entity, attribute_name)
    if existing_value is None:
        setattr(entity, attribute_name, expected_value)
        return
    if existing_value != expected_value:
        raise ValueError(
            f"Canonical Brandon Capital Partners entity already has conflicting {attribute_name} "
            f"({existing_value!r}); expected {expected_value!r}"
        )
