from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias, Fund, Holding, HoldingRelationship, InvestmentOption, SourceFile


IFM_CANONICAL_NAME = "IFM Investors Pty Ltd"
IFM_SEED_SOURCE = "ifm-stage3-v1"
IFM_ISSUER_RELATIONSHIP_ROLE = "issuer"
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
                source_system=IFM_SEED_SOURCE,
                source_file_id=None,
                is_preferred=is_preferred,
                match_confidence=Decimal("1.0"),
            )
        )
    session.flush()
    return entity


def ensure_ifm_art_sunsuper_issuer_relationship(
    session,
    *,
    ifm_entity_id: int | None = None,
) -> HoldingRelationship:
    entity = _get_ifm_entity(session, ifm_entity_id=ifm_entity_id)
    holding = _get_single_art_sunsuper_fixed_income_ifm_holding(session)
    if holding.entity_id != entity.id:
        raise ValueError(
            "The ART-Sunsuper IFM fixed-income row must already resolve to the canonical IFM entity "
            f"before seeding an issuer holding relationship; holding_id={holding.id} entity_id={holding.entity_id!r} "
            f"expected={entity.id}"
        )

    existing_relationship = session.scalar(
        select(HoldingRelationship).where(
            HoldingRelationship.holding_id == holding.id,
            HoldingRelationship.related_entity_id == entity.id,
            HoldingRelationship.relationship_role == IFM_ISSUER_RELATIONSHIP_ROLE,
        )
    )
    if existing_relationship is not None:
        return existing_relationship

    conflicting_relationship = session.scalar(
        select(HoldingRelationship).where(
            HoldingRelationship.holding_id == holding.id,
            HoldingRelationship.relationship_role == IFM_ISSUER_RELATIONSHIP_ROLE,
            HoldingRelationship.related_entity_id != entity.id,
        )
    )
    if conflicting_relationship is not None:
        raise ValueError(
            "Conflicting issuer holding_relationship already exists for the ART-Sunsuper IFM fixed-income row "
            f"(holding_id={holding.id}, related_entity_id={conflicting_relationship.related_entity_id})"
        )

    relationship = HoldingRelationship(
        holding_id=holding.id,
        related_entity_id=entity.id,
        relationship_role=IFM_ISSUER_RELATIONSHIP_ROLE,
        confidence_score=Decimal("1.0"),
        source=IFM_SEED_SOURCE,
    )
    session.add(relationship)
    session.flush()
    return relationship


def _get_ifm_entity(session, *, ifm_entity_id: int | None) -> Entity:
    if ifm_entity_id is not None:
        entity = session.get(Entity, ifm_entity_id)
        if entity is None:
            raise ValueError(f"Canonical IFM entity {ifm_entity_id} was not found")
    else:
        entity = session.query(Entity).filter(Entity.canonical_name == IFM_CANONICAL_NAME).one_or_none()
        if entity is None:
            raise ValueError("Canonical IFM entity has not been seeded yet")
    return entity


def _get_single_art_sunsuper_fixed_income_ifm_holding(session) -> Holding:
    holdings = session.scalars(
        select(Holding)
        .join(Fund, Fund.id == Holding.source_fund_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(SourceFile, SourceFile.id == Holding.source_file_id)
        .where(
            Fund.code == "art",
            InvestmentOption.source_option_name == "ART Stable",
            Holding.raw_name == IFM_CANONICAL_NAME,
            Holding.source_asset_class_raw == "Fixed Income",
            Holding.disclosure_completeness == "value_only",
            Holding.is_aggregate.is_(False),
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
        )
        .order_by(Holding.id.asc())
    ).all()
    if len(holdings) != 1:
        raise ValueError(
            "Expected exactly one current ART-Sunsuper fixed-income IFM holding row for the issuer-role seed; "
            f"found {len(holdings)}"
        )
    return holdings[0]
