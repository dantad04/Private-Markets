from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class SourceFileMetadata:
    source_file_id: str | int
    fund_id: str | int
    suspected_adapter_key: str
    reporting_period_id: str | int | None
    source_url: str
    checksum: str
    received_at: datetime
    reporting_period_end_date: date | None = None


@dataclass(frozen=True)
class SourceNormalisedHoldingRecord:
    source_file_id: str | int
    source_fund_id: str | int
    source_option_code: str
    source_option_name_raw: str
    reporting_period_date: date
    source_asset_class_raw: str
    source_subclass_raw: str | None
    canonical_asset_class_code: str
    is_aggregate: bool
    raw_name: str | None
    value_aud: Decimal | None
    ownership_pct: Decimal | None
    units: Decimal | None
    weighting_pct: Decimal | None
    currency_raw: str | None
    security_identifier_value: str | None
    security_identifier_type: str | None
    address_raw: str | None
    geo_lat: Decimal | None
    geo_lng: Decimal | None
    classification_raw: str | None
    location_raw: str | None
    value_band_raw: str | None
    disclosure_completeness: str
    source_row_number: int
    source_row_hash: str
    raw_payload_json: list[str] | list[dict[str, Any]]
    parse_warning_flags: list[str] = field(default_factory=list)
    metadata_attached_from_row_numbers: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class AdapterParseResult:
    holdings: list[SourceNormalisedHoldingRecord]
    structural_metadata: dict[str, Any]
    adapter_warnings: list[str]
    parse_statistics: dict[str, Any]
    schema_fingerprint: str


class BasePhdAdapter(Protocol):
    def parse(
        self,
        source_file_metadata: SourceFileMetadata,
        raw_bytes: bytes,
        approved_mapping_config: dict[str, Any] | None = None,
    ) -> AdapterParseResult: ...
