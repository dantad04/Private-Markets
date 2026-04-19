from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.admin import get_db_session
from app.read_models import EntityDetailReadModel, EntityObservationReadModel, get_entity_detail_by_name


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


@router.get("/by-name", response_model=EntityDetailResponse)
def entity_detail_by_name(
    name: str = Query(..., min_length=1, description="Case-insensitive exact raw holding name lookup"),
    session: Session = Depends(get_db_session),
) -> EntityDetailResponse:
    detail = get_entity_detail_by_name(session, name=name)
    if detail is None:
        raise HTTPException(status_code=404, detail="Entity observations not found")
    return EntityDetailResponse.from_read_model(detail)
