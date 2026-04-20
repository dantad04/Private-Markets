from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.admin import get_db_session
from app.read_models import (
    CanonicalEntityDetailReadModel,
    CrossAdapterHoldingsReadModel,
    CrossAdapterObservationReadModel,
    EntityObservedHoldingsCountReadModel,
    EntityRelationshipReadModel,
    EntityDetailReadModel,
    EntityObservationReadModel,
    get_canonical_entity_detail,
    get_cross_adapter_holdings_by_entity_id,
    get_cross_adapter_holdings_by_name,
    get_entity_detail_by_name,
)


router = APIRouter(prefix="/entities", tags=["entities"])


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


class EntityObservationResponse(BaseModel):
    raw_name: str
    source_file_id: int
    source_row_number: int
    fund_code: str
    fund_name: str
    option_name: str
    reporting_period_end_date: date
    canonical_asset_class_code: str
    source_asset_class_raw: str
    source_subclass_raw: str | None
    disclosure_completeness: str
    value_aud: str | None
    ownership_pct: str | None
    units: str | None
    value_band_raw: str | None
    currency_raw: str | None
    security_identifier_type: str | None
    security_identifier_value: str | None

    @classmethod
    def from_read_model(cls, item: EntityObservationReadModel) -> "EntityObservationResponse":
        return cls(
            raw_name=item.raw_name,
            source_file_id=item.source_file_id,
            source_row_number=item.source_row_number,
            fund_code=item.fund_code,
            fund_name=item.fund_name,
            option_name=item.option_name,
            reporting_period_end_date=item.reporting_period_end_date,
            canonical_asset_class_code=item.canonical_asset_class_code,
            source_asset_class_raw=item.source_asset_class_raw,
            source_subclass_raw=item.source_subclass_raw,
            disclosure_completeness=item.disclosure_completeness,
            value_aud=_decimal_string(item.value_aud),
            ownership_pct=_decimal_string(item.ownership_pct),
            units=_decimal_string(item.units),
            value_band_raw=item.value_band_raw,
            currency_raw=item.currency_raw,
            security_identifier_type=item.security_identifier_type,
            security_identifier_value=item.security_identifier_value,
        )


class EntityDetailResponse(BaseModel):
    lookup_name: str
    matched_names: list[str]
    observation_count: int
    latest_reporting_period: date | None
    disclosure_completeness_counts: dict[str, int]
    canonical_asset_class_counts: dict[str, int]
    observations: list[EntityObservationResponse]

    @classmethod
    def from_read_model(cls, item: EntityDetailReadModel) -> "EntityDetailResponse":
        return cls(
            lookup_name=item.lookup_name,
            matched_names=item.matched_names,
            observation_count=item.observation_count,
            latest_reporting_period=item.latest_reporting_period,
            disclosure_completeness_counts=item.disclosure_completeness_counts,
            canonical_asset_class_counts=item.canonical_asset_class_counts,
            observations=[EntityObservationResponse.from_read_model(row) for row in item.observations],
        )


class CrossAdapterObservationResponse(BaseModel):
    normalized_name: str
    raw_name: str
    source_file_id: int
    fund_code: str
    fund_name: str
    option_code: str
    option_name: str
    reporting_period_end_date: date
    disclosure_completeness: str
    value_aud: str | None
    ownership_pct: str | None
    value_band_raw: str | None
    is_aggregate: bool

    @classmethod
    def from_read_model(cls, item: CrossAdapterObservationReadModel) -> "CrossAdapterObservationResponse":
        return cls(
            normalized_name=item.normalized_name,
            raw_name=item.raw_name,
            source_file_id=item.source_file_id,
            fund_code=item.fund_code,
            fund_name=item.fund_name,
            option_code=item.option_code,
            option_name=item.option_name,
            reporting_period_end_date=item.reporting_period_end_date,
            disclosure_completeness=item.disclosure_completeness,
            value_aud=_decimal_string(item.value_aud),
            ownership_pct=_decimal_string(item.ownership_pct),
            value_band_raw=item.value_band_raw,
            is_aggregate=item.is_aggregate,
        )


class CrossAdapterHoldingsResponse(BaseModel):
    entity_id: int | None
    lookup_name: str
    normalized_lookup_name: str
    matched_normalized_names: list[str]
    matched_raw_names: list[str]
    observation_count: int
    fund_count: int
    observations: list[CrossAdapterObservationResponse]

    @classmethod
    def from_read_model(cls, item: CrossAdapterHoldingsReadModel) -> "CrossAdapterHoldingsResponse":
        return cls(
            entity_id=item.entity_id,
            lookup_name=item.lookup_name,
            normalized_lookup_name=item.normalized_lookup_name,
            matched_normalized_names=item.matched_normalized_names,
            matched_raw_names=item.matched_raw_names,
            observation_count=item.observation_count,
            fund_count=item.fund_count,
            observations=[CrossAdapterObservationResponse.from_read_model(row) for row in item.observations],
        )


class EntityRelationshipResponse(BaseModel):
    relationship_id: int
    from_entity_id: int
    to_entity_id: int
    relationship_type: str
    source: str
    notes: str | None

    @classmethod
    def from_read_model(cls, item: EntityRelationshipReadModel) -> "EntityRelationshipResponse":
        return cls(
            relationship_id=item.relationship_id,
            from_entity_id=item.from_entity_id,
            to_entity_id=item.to_entity_id,
            relationship_type=item.relationship_type,
            source=item.source,
            notes=item.notes,
        )


class EntityObservedHoldingsCountResponse(BaseModel):
    fund_code: str
    fund_name: str
    reporting_period_end_date: date
    observation_count: int

    @classmethod
    def from_read_model(cls, item: EntityObservedHoldingsCountReadModel) -> "EntityObservedHoldingsCountResponse":
        return cls(
            fund_code=item.fund_code,
            fund_name=item.fund_name,
            reporting_period_end_date=item.reporting_period_end_date,
            observation_count=item.observation_count,
        )


class CanonicalEntityDetailResponse(BaseModel):
    entity_id: int
    canonical_name: str
    entity_type: str
    abn: str | None
    aliases: list[str]
    relationships: list[EntityRelationshipResponse]
    observed_holdings_count_by_fund_period: list[EntityObservedHoldingsCountResponse]

    @classmethod
    def from_read_model(cls, item: CanonicalEntityDetailReadModel) -> "CanonicalEntityDetailResponse":
        return cls(
            entity_id=item.entity_id,
            canonical_name=item.canonical_name,
            entity_type=item.entity_type,
            abn=item.abn,
            aliases=item.aliases,
            relationships=[EntityRelationshipResponse.from_read_model(row) for row in item.relationships],
            observed_holdings_count_by_fund_period=[
                EntityObservedHoldingsCountResponse.from_read_model(row)
                for row in item.observed_holdings_count_by_fund_period
            ],
        )


@router.get("/by-name", response_model=EntityDetailResponse)
def entity_detail_by_name(
    name: str = Query(..., min_length=1, description="Case-insensitive exact raw holding name lookup"),
    session: Session = Depends(get_db_session),
) -> EntityDetailResponse:
    detail = get_entity_detail_by_name(session, name=name)
    if detail is None:
        raise HTTPException(status_code=404, detail="Entity observations not found")
    return EntityDetailResponse.from_read_model(detail)


@router.get("/cross-adapter", response_model=CrossAdapterHoldingsResponse)
def cross_adapter_holdings_by_name(
    name: str | None = Query(
        None,
        min_length=1,
        description="Conservative raw-name lookup across loaded current source files",
    ),
    entity_id: int | None = Query(None, ge=1, description="Canonical entity id lookup across aliases and linked holdings"),
    session: Session = Depends(get_db_session),
) -> CrossAdapterHoldingsResponse:
    if entity_id is not None:
        detail = get_cross_adapter_holdings_by_entity_id(session, entity_id=entity_id)
    elif name is not None:
        detail = get_cross_adapter_holdings_by_name(session, name=name)
    else:
        raise HTTPException(status_code=400, detail="Provide either name or entity_id")
    if detail is None:
        raise HTTPException(status_code=404, detail="Cross-adapter holdings not found")
    return CrossAdapterHoldingsResponse.from_read_model(detail)


@router.get("/{entity_id}", response_model=CanonicalEntityDetailResponse)
def canonical_entity_detail(
    entity_id: int,
    session: Session = Depends(get_db_session),
) -> CanonicalEntityDetailResponse:
    detail = get_canonical_entity_detail(session, entity_id=entity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return CanonicalEntityDetailResponse.from_read_model(detail)
