from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.admin import get_db_session
from app.read_models import (
    FundAssetClassMixBucketReadModel,
    FundAssetClassMixReadModel,
    FundChangeReadModel,
    FundDetailReadModel,
    FundInvestmentOptionReadModel,
    FundObservationSummaryReadModel,
    get_fund_detail,
)


router = APIRouter(prefix="/funds", tags=["funds"])


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


class FundAssetClassMixBucketResponse(BaseModel):
    disclosure_completeness: str
    observation_count: int
    precise_value_row_count: int
    precise_value_aud_total: str

    @classmethod
    def from_read_model(cls, item: FundAssetClassMixBucketReadModel) -> "FundAssetClassMixBucketResponse":
        return cls(
            disclosure_completeness=item.disclosure_completeness,
            observation_count=item.observation_count,
            precise_value_row_count=item.precise_value_row_count,
            precise_value_aud_total=_decimal_string(item.precise_value_aud_total) or "0",
        )


class FundAssetClassMixResponse(BaseModel):
    canonical_asset_class_code: str
    by_disclosure_completeness: list[FundAssetClassMixBucketResponse]

    @classmethod
    def from_read_model(cls, item: FundAssetClassMixReadModel) -> "FundAssetClassMixResponse":
        return cls(
            canonical_asset_class_code=item.canonical_asset_class_code,
            by_disclosure_completeness=[
                FundAssetClassMixBucketResponse.from_read_model(bucket)
                for bucket in item.by_disclosure_completeness
            ],
        )


class FundObservationSummaryResponse(BaseModel):
    raw_name: str
    entity_id: int | None
    entity_canonical_name: str | None
    entity_type: str | None
    source_file_id: int
    source_row_number: int
    reporting_period_end_date: date
    canonical_asset_class_code: str
    source_asset_class_raw: str
    source_subclass_raw: str | None
    classification_raw: str | None
    disclosure_completeness: str
    observation_kind: str
    value_aud: str | None
    ownership_pct: str | None
    value_band_raw: str | None

    @classmethod
    def from_read_model(cls, item: FundObservationSummaryReadModel) -> "FundObservationSummaryResponse":
        return cls(
            raw_name=item.raw_name,
            entity_id=item.entity_id,
            entity_canonical_name=item.entity_canonical_name,
            entity_type=item.entity_type,
            source_file_id=item.source_file_id,
            source_row_number=item.source_row_number,
            reporting_period_end_date=item.reporting_period_end_date,
            canonical_asset_class_code=item.canonical_asset_class_code,
            source_asset_class_raw=item.source_asset_class_raw,
            source_subclass_raw=item.source_subclass_raw,
            classification_raw=item.classification_raw,
            disclosure_completeness=item.disclosure_completeness,
            observation_kind=item.observation_kind,
            value_aud=_decimal_string(item.value_aud),
            ownership_pct=_decimal_string(item.ownership_pct),
            value_band_raw=item.value_band_raw,
        )


class FundInvestmentOptionResponse(BaseModel):
    option_id: int
    option_code: str
    option_name: str
    reporting_period_end_date: date | None
    observation_count: int
    asset_class_mix: list[FundAssetClassMixResponse]
    top_direct_private_holdings: list[FundObservationSummaryResponse]
    manager_level_aggregate_exposures: list[FundObservationSummaryResponse]
    named_private_exposures: list[FundObservationSummaryResponse]

    @classmethod
    def from_read_model(cls, item: FundInvestmentOptionReadModel) -> "FundInvestmentOptionResponse":
        return cls(
            option_id=item.option_id,
            option_code=item.option_code,
            option_name=item.option_name,
            reporting_period_end_date=item.reporting_period_end_date,
            observation_count=item.observation_count,
            asset_class_mix=[FundAssetClassMixResponse.from_read_model(row) for row in item.asset_class_mix],
            top_direct_private_holdings=[
                FundObservationSummaryResponse.from_read_model(row) for row in item.top_direct_private_holdings
            ],
            manager_level_aggregate_exposures=[
                FundObservationSummaryResponse.from_read_model(row)
                for row in item.manager_level_aggregate_exposures
            ],
            named_private_exposures=[
                FundObservationSummaryResponse.from_read_model(row) for row in item.named_private_exposures
            ],
        )


class FundChangeResponse(BaseModel):
    available: bool
    current_reporting_period_end_date: date | None
    prior_reporting_period_end_date: date | None
    note: str | None

    @classmethod
    def from_read_model(cls, item: FundChangeReadModel) -> "FundChangeResponse":
        return cls(
            available=item.available,
            current_reporting_period_end_date=item.current_reporting_period_end_date,
            prior_reporting_period_end_date=item.prior_reporting_period_end_date,
            note=item.note,
        )


class FundDetailResponse(BaseModel):
    fund_id: int
    fund_code: str
    fund_name: str
    latest_reporting_period: date | None
    investment_options: list[FundInvestmentOptionResponse]
    change_since_prior_reporting_period: FundChangeResponse

    @classmethod
    def from_read_model(cls, item: FundDetailReadModel) -> "FundDetailResponse":
        return cls(
            fund_id=item.fund_id,
            fund_code=item.fund_code,
            fund_name=item.fund_name,
            latest_reporting_period=item.latest_reporting_period,
            investment_options=[FundInvestmentOptionResponse.from_read_model(row) for row in item.investment_options],
            change_since_prior_reporting_period=FundChangeResponse.from_read_model(
                item.change_since_prior_reporting_period
            ),
        )


@router.get("/{fund_code}", response_model=FundDetailResponse)
def fund_detail(
    fund_code: str,
    session: Session = Depends(get_db_session),
) -> FundDetailResponse:
    detail = get_fund_detail(session, fund_code=fund_code)
    if detail is None:
        raise HTTPException(status_code=404, detail="Fund detail not found")
    return FundDetailResponse.from_read_model(detail)
