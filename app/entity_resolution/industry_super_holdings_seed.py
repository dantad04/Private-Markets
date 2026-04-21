from __future__ import annotations

from datetime import date
from decimal import Decimal

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias
from app.entity_resolution.deterministic import normalise_abn


INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME = "Industry Super Holdings Pty Ltd"
INDUSTRY_SUPER_HOLDINGS_SEED_SOURCE = "industry-super-holdings-stage5-v1"
INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN = "71 119 748 060"
INDUSTRY_SUPER_HOLDINGS_REVIEW_SOURCE = "manual review against the Australian Business Register public record"
INDUSTRY_SUPER_HOLDINGS_REVIEWED_BY = "dan"
INDUSTRY_SUPER_HOLDINGS_REVIEWED_AT = date(2026, 4, 21)
INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR = "INDUSTRY SUPER HOLDINGS PTY. LTD."
INDUSTRY_SUPER_HOLDINGS_LEGACY_NOTES = (
    "Stage 3 Industry Super Holdings canonical seed. ABN intentionally left null in this run because it was not "
    "verified from approved repo-backed source material."
)
INDUSTRY_SUPER_HOLDINGS_NOTES = (
    "Stage 5 Industry Super Holdings proof-slice seed. Reviewed ABN and ABR provenance are persisted on the "
    "canonical entity."
)
INDUSTRY_SUPER_HOLDINGS_OBSERVED_ALIASES: tuple[tuple[str, bool], ...] = (
    ("Industry Super Holdings Pty Ltd", True),
    ("Industry Super Holdings", False),
    ("Industry Super Holdings Pty Ltd F/P", False),
)


def ensure_industry_super_holdings_seed(session) -> Entity:
    entity = session.query(Entity).filter(
        Entity.canonical_name == INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME
    ).one_or_none()
    if entity is None:
        entity = Entity(
            entity_type="company",
            canonical_name=INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME,
            abn=INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN,
            abn_review_source=INDUSTRY_SUPER_HOLDINGS_REVIEW_SOURCE,
            abn_reviewed_by=INDUSTRY_SUPER_HOLDINGS_REVIEWED_BY,
            abn_reviewed_at=INDUSTRY_SUPER_HOLDINGS_REVIEWED_AT,
            registered_name_on_abr=INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR,
            country_code="AU",
            is_australian_entity=True,
            confidence_tier="seeded",
            notes=INDUSTRY_SUPER_HOLDINGS_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_industry_super_holdings_reviewed_identity(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.query(EntityAlias.alias).filter(EntityAlias.entity_id == entity.id).all()
    }

    for alias, is_preferred in INDUSTRY_SUPER_HOLDINGS_OBSERVED_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=INDUSTRY_SUPER_HOLDINGS_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )
    session.flush()
    return entity


def _ensure_industry_super_holdings_reviewed_identity(entity: Entity) -> None:
    if normalise_abn(entity.abn) != normalise_abn(INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN):
        entity.abn = INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN

    if entity.registered_name_on_abr != INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR:
        entity.registered_name_on_abr = INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR

    _overwrite_or_fill(
        entity=entity,
        attribute_name="abn_review_source",
        expected_value=INDUSTRY_SUPER_HOLDINGS_REVIEW_SOURCE,
    )
    _overwrite_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_by",
        expected_value=INDUSTRY_SUPER_HOLDINGS_REVIEWED_BY,
    )
    _overwrite_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_at",
        expected_value=INDUSTRY_SUPER_HOLDINGS_REVIEWED_AT,
    )

    if entity.is_australian_entity is False:
        raise ValueError(
            "Canonical Industry Super Holdings entity is marked non-Australian despite reviewed ABR registration"
        )
    if entity.is_australian_entity is None:
        entity.is_australian_entity = True
    if entity.country_code in {None, ""}:
        entity.country_code = "AU"
    if entity.notes in {None, INDUSTRY_SUPER_HOLDINGS_LEGACY_NOTES}:
        entity.notes = INDUSTRY_SUPER_HOLDINGS_NOTES


def _overwrite_or_fill(entity: Entity, *, attribute_name: str, expected_value: object) -> None:
    existing_value = getattr(entity, attribute_name)
    if existing_value != expected_value:
        setattr(entity, attribute_name, expected_value)
