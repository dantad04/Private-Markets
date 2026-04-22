from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias
from app.entity_resolution.deterministic import normalise_abn


SQUARE_PEG_CAPITAL_CANONICAL_NAME = "Square Peg Capital"
SQUARE_PEG_CAPITAL_SEED_SOURCE = "square-peg-capital-stage5-v1"
SQUARE_PEG_CAPITAL_REVIEWED_ABN = "51 164 352 229"
SQUARE_PEG_CAPITAL_REVIEW_SOURCE = "manual review against the Australian Business Register public record"
SQUARE_PEG_CAPITAL_REVIEWED_BY = "codex"
SQUARE_PEG_CAPITAL_REVIEWED_AT = date(2026, 4, 22)
SQUARE_PEG_CAPITAL_REGISTERED_NAME_ON_ABR = "SQUARE PEG CAPITAL PTY LTD"
SQUARE_PEG_CAPITAL_CURRENT_LEGAL_ALIAS = "Square Peg Capital Pty Ltd"
SQUARE_PEG_CAPITAL_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only from current Square Peg "
    "manager-scoped observations; no reviewed ABR or ASIC enrichment is persisted on this entity."
)
SQUARE_PEG_CAPITAL_NOTES = (
    "Stage 5 Square Peg Capital reviewed identity proof slice. The existing canonical manager entity is "
    "enriched in place to the current ABR legal identity, with the current legal-form alias retained as "
    "a non-preferred exact-name variant."
)
SQUARE_PEG_CAPITAL_ALIASES: tuple[tuple[str, bool], ...] = (
    (SQUARE_PEG_CAPITAL_CANONICAL_NAME, True),
    (SQUARE_PEG_CAPITAL_CURRENT_LEGAL_ALIAS, False),
)


def ensure_square_peg_capital_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == SQUARE_PEG_CAPITAL_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="manager",
            canonical_name=SQUARE_PEG_CAPITAL_CANONICAL_NAME,
            abn=SQUARE_PEG_CAPITAL_REVIEWED_ABN,
            abn_review_source=SQUARE_PEG_CAPITAL_REVIEW_SOURCE,
            abn_reviewed_by=SQUARE_PEG_CAPITAL_REVIEWED_BY,
            abn_reviewed_at=SQUARE_PEG_CAPITAL_REVIEWED_AT,
            registered_name_on_abr=SQUARE_PEG_CAPITAL_REGISTERED_NAME_ON_ABR,
            country_code="AU",
            is_australian_entity=True,
            confidence_tier="seeded",
            notes=SQUARE_PEG_CAPITAL_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_square_peg_capital_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in SQUARE_PEG_CAPITAL_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=SQUARE_PEG_CAPITAL_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_square_peg_capital_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "manager":
        raise ValueError(
            "Canonical Square Peg Capital entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'manager'"
        )

    if normalise_abn(entity.abn) not in {None, normalise_abn(SQUARE_PEG_CAPITAL_REVIEWED_ABN)}:
        raise ValueError(
            "Canonical Square Peg Capital entity already has a conflicting reviewed ABN "
            f"({entity.abn!r}); expected {SQUARE_PEG_CAPITAL_REVIEWED_ABN!r}"
        )
    if entity.abn is None:
        entity.abn = SQUARE_PEG_CAPITAL_REVIEWED_ABN

    if entity.registered_name_on_abr not in {None, SQUARE_PEG_CAPITAL_REGISTERED_NAME_ON_ABR}:
        raise ValueError(
            "Canonical Square Peg Capital entity already has conflicting ABR registered-name provenance "
            f"({entity.registered_name_on_abr!r}); expected {SQUARE_PEG_CAPITAL_REGISTERED_NAME_ON_ABR!r}"
        )
    if entity.registered_name_on_abr is None:
        entity.registered_name_on_abr = SQUARE_PEG_CAPITAL_REGISTERED_NAME_ON_ABR

    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_review_source",
        expected_value=SQUARE_PEG_CAPITAL_REVIEW_SOURCE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_by",
        expected_value=SQUARE_PEG_CAPITAL_REVIEWED_BY,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_at",
        expected_value=SQUARE_PEG_CAPITAL_REVIEWED_AT,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="confidence_tier",
        expected_value="seeded",
    )

    if entity.is_australian_entity is False:
        raise ValueError(
            "Canonical Square Peg Capital entity is marked non-Australian despite current manager-scoped "
            "Australian private-market observations"
        )
    if entity.is_australian_entity is None:
        entity.is_australian_entity = True
    if entity.country_code not in {None, "", "AU"}:
        raise ValueError(
            "Canonical Square Peg Capital entity already has a conflicting country_code "
            f"({entity.country_code!r}); expected None or 'AU'"
        )
    if entity.country_code in {None, ""}:
        entity.country_code = "AU"
    if entity.notes in {None, SQUARE_PEG_CAPITAL_LEGACY_NOTES}:
        entity.notes = SQUARE_PEG_CAPITAL_NOTES


def _ensure_matching_or_fill(entity: Entity, *, attribute_name: str, expected_value: object) -> None:
    existing_value = getattr(entity, attribute_name)
    if existing_value is None:
        setattr(entity, attribute_name, expected_value)
        return
    if existing_value != expected_value:
        raise ValueError(
            f"Canonical Square Peg Capital entity already has conflicting {attribute_name} "
            f"({existing_value!r}); expected {expected_value!r}"
        )
