from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db.models import CanonicalAssetClass, Entity, Fund, Holding, HoldingRelationship, InvestmentOption, ReportingPeriod, SourceFile
from app.ingest.governance import AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID


AUSTRALIANSUPER_STABLE_MATCHED_ASSET_PROOF_KEY = "australiansuper-stable-stage5-proof"
AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE = "australiansuper-stable-stage5-matched-asset-proof-v1"
AUSTRALIANSUPER_STABLE_MATCHED_ASSET_RELATIONSHIP_ROLE = "property_asset_match"
AUSTRALIANSUPER_STABLE_MATCHED_ASSET_CONFIDENCE = Decimal("1.0")
AUSTRALIANSUPER_STABLE_TARGET_PERIOD_END_DATE = date(2025, 12, 31)
AUSTRALIANSUPER_STABLE_FIXTURE_FILENAME = "Stable PHD (1).csv"


@dataclass(frozen=True)
class AustralianSuperStableMatchedAssetTarget:
    source_row_number: int
    asset_name: str
    entity_type: str
    canonical_asset_class_code: str
    source_asset_class_raw: str
    source_subclass_raw: str
    classification_raw: str


AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGETS: tuple[AustralianSuperStableMatchedAssetTarget, ...] = (
    AustralianSuperStableMatchedAssetTarget(
        source_row_number=3368,
        asset_name="1200 W Carroll",
        entity_type="property_asset",
        canonical_asset_class_code="unlisted_property",
        source_asset_class_raw="Unlisted Property",
        source_subclass_raw="Internally Managed",
        classification_raw="Office",
    ),
    AustralianSuperStableMatchedAssetTarget(
        source_row_number=3369,
        asset_name="1300 W Carroll",
        entity_type="property_asset",
        canonical_asset_class_code="unlisted_property",
        source_asset_class_raw="Unlisted Property",
        source_subclass_raw="Internally Managed",
        classification_raw="Office",
    ),
    AustralianSuperStableMatchedAssetTarget(
        source_row_number=3375,
        asset_name="Ala Moana Shopping Centre",
        entity_type="property_asset",
        canonical_asset_class_code="unlisted_property",
        source_asset_class_raw="Unlisted Property",
        source_subclass_raw="Internally Managed",
        classification_raw="Retail",
    ),
    AustralianSuperStableMatchedAssetTarget(
        source_row_number=3425,
        asset_name="Kingswood",
        entity_type="property_asset",
        canonical_asset_class_code="unlisted_property",
        source_asset_class_raw="Unlisted Property",
        source_subclass_raw="Internally Managed",
        classification_raw="Residential",
    ),
    AustralianSuperStableMatchedAssetTarget(
        source_row_number=3445,
        asset_name="NSW Ports",
        entity_type="infrastructure_asset",
        canonical_asset_class_code="unlisted_infrastructure",
        source_asset_class_raw="Unlisted Infrastructure",
        source_subclass_raw="Internally Managed",
        classification_raw="Seaport",
    ),
    AustralianSuperStableMatchedAssetTarget(
        source_row_number=3453,
        asset_name="Perth Airport",
        entity_type="infrastructure_asset",
        canonical_asset_class_code="unlisted_infrastructure",
        source_asset_class_raw="Unlisted Infrastructure",
        source_subclass_raw="Internally Managed",
        classification_raw="Airport",
    ),
    AustralianSuperStableMatchedAssetTarget(
        source_row_number=3484,
        asset_name="Wollert",
        entity_type="property_asset",
        canonical_asset_class_code="unlisted_property",
        source_asset_class_raw="Unlisted Property",
        source_subclass_raw="Internally Managed",
        classification_raw="Residential",
    ),
)
AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGET_ROW_NUMBERS = tuple(
    target.source_row_number for target in AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGETS
)
_TARGETS_BY_ROW_NUMBER = {
    target.source_row_number: target for target in AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGETS
}


def ensure_australiansuper_stable_matched_asset_proof(session) -> list[HoldingRelationship]:
    holdings_by_row_number = _load_current_stable_target_holdings(session)
    relationships: list[HoldingRelationship] = []

    for target in AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGETS:
        holding, asset_class_code = holdings_by_row_number[target.source_row_number]
        _validate_target_holding(holding=holding, asset_class_code=asset_class_code, target=target)
        entity = _ensure_asset_entity(session, target=target)
        relationships.append(_ensure_asset_relationship(session, holding=holding, entity=entity, target=target))

    session.flush()
    return relationships


def _load_current_stable_target_holdings(session) -> dict[int, tuple[Holding, str]]:
    rows = session.execute(
        select(Holding, CanonicalAssetClass.code, SourceFile)
        .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
        .join(SourceFile, SourceFile.id == Holding.source_file_id)
        .join(Fund, Fund.id == Holding.source_fund_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
        .where(
            Fund.code == "australiansuper",
            SourceFile.adapter_key == "AustralianSuperPhdAdapter",
            SourceFile.mapping_version_id == AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID,
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
            InvestmentOption.source_option_code == "ARST",
            InvestmentOption.source_option_name == "Stable",
            ReportingPeriod.period_end_date == AUSTRALIANSUPER_STABLE_TARGET_PERIOD_END_DATE,
            Holding.source_row_number.in_(AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGET_ROW_NUMBERS),
            Holding.is_aggregate.is_(False),
        )
    ).all()

    by_row_number: dict[int, tuple[Holding, str]] = {}
    for holding, asset_class_code, source_file in rows:
        if Path(str(source_file.source_url)).name != AUSTRALIANSUPER_STABLE_FIXTURE_FILENAME:
            raise ValueError(
                "AustralianSuper Stable matched-asset proof requires the approved Stable real fixture; "
                f"source_file_id={source_file.id} source_url={source_file.source_url!r}"
            )
        if holding.source_row_number in by_row_number:
            raise ValueError(
                "AustralianSuper Stable matched-asset proof expected one holding per target source row; "
                f"found duplicate row {holding.source_row_number}"
            )
        by_row_number[holding.source_row_number] = (holding, asset_class_code)

    missing = sorted(set(AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGET_ROW_NUMBERS) - set(by_row_number))
    if missing:
        raise ValueError(
            "AustralianSuper Stable matched-asset proof could not identify every target row through the "
            f"approved Stable ingest path; missing source rows {missing}"
        )
    return by_row_number


def _validate_target_holding(
    *,
    holding: Holding,
    asset_class_code: str,
    target: AustralianSuperStableMatchedAssetTarget,
) -> None:
    expected_values = {
        "raw_name": target.asset_name,
        "source_asset_class_raw": target.source_asset_class_raw,
        "source_subclass_raw": target.source_subclass_raw,
        "disclosure_completeness": "ownership_only",
        "classification_raw": target.classification_raw,
    }
    for attribute_name, expected_value in expected_values.items():
        actual_value = getattr(holding, attribute_name)
        if actual_value != expected_value:
            raise ValueError(
                "AustralianSuper Stable matched-asset proof target row shape changed; "
                f"row={target.source_row_number} field={attribute_name} actual={actual_value!r} "
                f"expected={expected_value!r}"
            )
    if asset_class_code != target.canonical_asset_class_code:
        raise ValueError(
            "AustralianSuper Stable matched-asset proof target row changed canonical asset class; "
            f"row={target.source_row_number} actual={asset_class_code!r} "
            f"expected={target.canonical_asset_class_code!r}"
        )
    if holding.geo_lat is None or holding.geo_lng is None:
        raise ValueError(
            "AustralianSuper Stable matched-asset proof target row must be coordinate-backed; "
            f"row={target.source_row_number}"
        )


def _ensure_asset_entity(session, *, target: AustralianSuperStableMatchedAssetTarget) -> Entity:
    entities = session.scalars(
        select(Entity).where(Entity.canonical_name == target.asset_name).order_by(Entity.id.asc())
    ).all()
    if len(entities) > 1:
        raise ValueError(
            "AustralianSuper Stable matched-asset proof found multiple canonical entities for "
            f"{target.asset_name!r}; refusing to choose between them"
        )

    if entities:
        entity = entities[0]
        if entity.entity_type != target.entity_type:
            raise ValueError(
                "AustralianSuper Stable matched-asset proof found an existing entity with a conflicting type; "
                f"name={target.asset_name!r} actual={entity.entity_type!r} expected={target.entity_type!r}"
            )
    else:
        entity = Entity(
            entity_type=target.entity_type,
            canonical_name=target.asset_name,
            confidence_tier="seeded",
            notes=(
                "Stage 5 bounded AustralianSuper Stable matched-asset proof seed. Exact source-row scoped; "
                "not a cross-fund, cross-option, or geocoded asset match."
            ),
        )
        session.add(entity)
        session.flush()

    if entity.confidence_tier is None:
        entity.confidence_tier = "seeded"
    if entity.notes is None:
        entity.notes = (
            "Stage 5 bounded AustralianSuper Stable matched-asset proof seed. Exact source-row scoped; "
            "not a cross-fund, cross-option, or geocoded asset match."
        )
    return entity


def _ensure_asset_relationship(
    session,
    *,
    holding: Holding,
    entity: Entity,
    target: AustralianSuperStableMatchedAssetTarget,
) -> HoldingRelationship:
    existing_relationship = session.scalar(
        select(HoldingRelationship).where(
            HoldingRelationship.holding_id == holding.id,
            HoldingRelationship.relationship_role == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_RELATIONSHIP_ROLE,
        )
    )
    if existing_relationship is not None:
        if existing_relationship.related_entity_id != entity.id:
            raise ValueError(
                "AustralianSuper Stable matched-asset proof found a conflicting asset match relationship; "
                f"row={target.source_row_number} holding_id={holding.id} "
                f"actual_entity_id={existing_relationship.related_entity_id} expected_entity_id={entity.id}"
            )
        if existing_relationship.source != AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE:
            raise ValueError(
                "AustralianSuper Stable matched-asset proof found an existing relationship with an unexpected source; "
                f"row={target.source_row_number} source={existing_relationship.source!r}"
            )
        if existing_relationship.confidence_score != AUSTRALIANSUPER_STABLE_MATCHED_ASSET_CONFIDENCE:
            raise ValueError(
                "AustralianSuper Stable matched-asset proof found an existing relationship with unexpected confidence; "
                f"row={target.source_row_number} confidence={existing_relationship.confidence_score!r}"
            )
        return existing_relationship

    relationship = HoldingRelationship(
        holding_id=holding.id,
        related_entity_id=entity.id,
        relationship_role=AUSTRALIANSUPER_STABLE_MATCHED_ASSET_RELATIONSHIP_ROLE,
        confidence_score=AUSTRALIANSUPER_STABLE_MATCHED_ASSET_CONFIDENCE,
        source=AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE,
    )
    session.add(relationship)
    session.flush()
    return relationship
