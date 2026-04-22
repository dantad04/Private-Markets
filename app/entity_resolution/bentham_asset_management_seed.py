from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias
from app.entity_resolution.deterministic import normalise_abn


BENTHAM_ASSET_MANAGEMENT_CANONICAL_NAME = "Bentham Asset Management Pty Ltd"
BENTHAM_ASSET_MANAGEMENT_SEED_SOURCE = "bentham-asset-management-stage5-v1"
BENTHAM_ASSET_MANAGEMENT_REVIEWED_ABN = "92 140 833 674"
BENTHAM_ASSET_MANAGEMENT_REVIEW_SOURCE = "manual review against the Australian Business Register public record"
BENTHAM_ASSET_MANAGEMENT_REVIEWED_BY = "codex"
BENTHAM_ASSET_MANAGEMENT_REVIEWED_AT = date(2026, 4, 22)
BENTHAM_ASSET_MANAGEMENT_REGISTERED_NAME_ON_ABR = "BENTHAM ASSET MANAGEMENT PTY LTD"
BENTHAM_ASSET_MANAGEMENT_HISTORICAL_NAME_ON_ABR = "Challenger Alpha RE AFSL Pty Limited"
BENTHAM_ASSET_MANAGEMENT_LEGACY_NOTES = (
    "Stage 5 canonical manager dependency slice. Exact observed aliases only; no reviewed ABR or ASIC "
    "enrichment is persisted on this entity."
)
BENTHAM_ASSET_MANAGEMENT_NOTES = (
    "Stage 5 Bentham Asset Management reviewed identity proof slice. The existing canonical manager entity is "
    "enriched in place to the current ABR legal identity, with the prior ABR historical name retained as a "
    "non-preferred alias."
)
BENTHAM_ASSET_MANAGEMENT_ALIASES: tuple[tuple[str, bool], ...] = (
    ("Bentham Asset Management Pty Ltd", True),
    ("Challenger Alpha RE AFSL Pty Limited", False),
)


def ensure_bentham_asset_management_seed(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == BENTHAM_ASSET_MANAGEMENT_CANONICAL_NAME,
        )
    )
    if entity is None:
        entity = Entity(
            entity_type="manager",
            canonical_name=BENTHAM_ASSET_MANAGEMENT_CANONICAL_NAME,
            abn=BENTHAM_ASSET_MANAGEMENT_REVIEWED_ABN,
            abn_review_source=BENTHAM_ASSET_MANAGEMENT_REVIEW_SOURCE,
            abn_reviewed_by=BENTHAM_ASSET_MANAGEMENT_REVIEWED_BY,
            abn_reviewed_at=BENTHAM_ASSET_MANAGEMENT_REVIEWED_AT,
            registered_name_on_abr=BENTHAM_ASSET_MANAGEMENT_REGISTERED_NAME_ON_ABR,
            country_code="AU",
            is_australian_entity=True,
            confidence_tier="seeded",
            notes=BENTHAM_ASSET_MANAGEMENT_NOTES,
        )
        session.add(entity)
        session.flush()

    _ensure_bentham_asset_management_seed_shape(entity)

    existing_alias_values = {
        alias_value
        for (alias_value,) in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity.id)
        ).all()
    }
    for alias, is_preferred in BENTHAM_ASSET_MANAGEMENT_ALIASES:
        if alias in existing_alias_values:
            continue
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                alias_normalized=normalise_name(alias),
                source_system=BENTHAM_ASSET_MANAGEMENT_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )

    session.flush()
    return entity


def _ensure_bentham_asset_management_seed_shape(entity: Entity) -> None:
    if entity.entity_type != "manager":
        raise ValueError(
            "Canonical Bentham Asset Management entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'manager'"
        )

    if normalise_abn(entity.abn) not in {None, normalise_abn(BENTHAM_ASSET_MANAGEMENT_REVIEWED_ABN)}:
        raise ValueError(
            "Canonical Bentham Asset Management entity already has a conflicting reviewed ABN "
            f"({entity.abn!r}); expected {BENTHAM_ASSET_MANAGEMENT_REVIEWED_ABN!r}"
        )
    if entity.abn is None:
        entity.abn = BENTHAM_ASSET_MANAGEMENT_REVIEWED_ABN

    if entity.registered_name_on_abr not in {None, BENTHAM_ASSET_MANAGEMENT_REGISTERED_NAME_ON_ABR}:
        raise ValueError(
            "Canonical Bentham Asset Management entity already has conflicting ABR registered-name provenance "
            f"({entity.registered_name_on_abr!r}); expected {BENTHAM_ASSET_MANAGEMENT_REGISTERED_NAME_ON_ABR!r}"
        )
    if entity.registered_name_on_abr is None:
        entity.registered_name_on_abr = BENTHAM_ASSET_MANAGEMENT_REGISTERED_NAME_ON_ABR

    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_review_source",
        expected_value=BENTHAM_ASSET_MANAGEMENT_REVIEW_SOURCE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_by",
        expected_value=BENTHAM_ASSET_MANAGEMENT_REVIEWED_BY,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="abn_reviewed_at",
        expected_value=BENTHAM_ASSET_MANAGEMENT_REVIEWED_AT,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="confidence_tier",
        expected_value="seeded",
    )

    if entity.is_australian_entity is False:
        raise ValueError(
            "Canonical Bentham Asset Management entity is marked non-Australian despite reviewed ABR registration"
        )
    if entity.is_australian_entity is None:
        entity.is_australian_entity = True
    if entity.country_code in {None, ""}:
        entity.country_code = "AU"
    if entity.notes in {None, BENTHAM_ASSET_MANAGEMENT_LEGACY_NOTES}:
        entity.notes = BENTHAM_ASSET_MANAGEMENT_NOTES


def _ensure_matching_or_fill(entity: Entity, *, attribute_name: str, expected_value: object) -> None:
    existing_value = getattr(entity, attribute_name)
    if existing_value is None:
        setattr(entity, attribute_name, expected_value)
        return
    if existing_value != expected_value:
        raise ValueError(
            f"Canonical Bentham Asset Management entity already has conflicting {attribute_name} "
            f"({existing_value!r}); expected {expected_value!r}"
        )
