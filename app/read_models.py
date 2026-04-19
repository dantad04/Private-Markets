from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CanonicalAssetClass, Fund, Holding, InvestmentOption, ReportingPeriod, SourceFile


@dataclass(frozen=True)
class SourceFileListItem:
    id: int
    fund_code: str
    fund_name: str
    adapter_key: str
    schema_fingerprint: str | None
    mapping_version_id: str | None
    ingest_status: str
    period_end_date: date | None
    received_at: datetime
    encoding_replacement_count: int
    rows_loaded: int
    version_number: int
    is_current_version: bool


@dataclass(frozen=True)
class SourceFileSummary:
    id: int
    fund_id: int
    fund_code: str
    fund_name: str
    investment_option_id: int | None
    investment_option_name: str | None
    adapter_key: str
    source_url: str
    checksum: str
    ingest_status: str
    schema_fingerprint: str | None
    mapping_version_id: str | None
    reporting_period_id: int | None
    reporting_period_end_date: date | None
    publication_date: date | None
    terms_snapshot_url: str | None
    downloaded_at: datetime | None
    received_at: datetime
    encoding_replacement_count: int
    version_number: int
    is_current_version: bool
    supersedes_source_file_id: int | None


@dataclass(frozen=True)
class SourceFileHoldingRow:
    source_option_code: str
    source_option_name: str
    source_row_number: int
    raw_name: str | None
    source_asset_class_raw: str
    source_subclass_raw: str | None
    canonical_asset_class_code: str
    disclosure_completeness: str
    is_aggregate: bool
    value_aud: Decimal | None
    ownership_pct: Decimal | None
    currency_raw: str | None
    security_identifier_type: str | None
    security_identifier_value: str | None
    value_band_raw: str | None
    raw_payload_json: list[dict[str, object]]
    metadata_attached_from_row_numbers: list[int]
    ingested_at: datetime


@dataclass(frozen=True)
class SourceFileDetailReadModel:
    source_file: SourceFileSummary
    disclosure_counts: list[tuple[str, int]]
    canonical_asset_class_counts: list[tuple[str, int]]
    holdings: list[SourceFileHoldingRow]
    page: int
    size: int
    total_rows: int
    total_pages: int


@dataclass(frozen=True)
class EntityObservationReadModel:
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
    value_aud: Decimal | None
    ownership_pct: Decimal | None
    units: Decimal | None
    value_band_raw: str | None
    currency_raw: str | None
    security_identifier_type: str | None
    security_identifier_value: str | None


@dataclass(frozen=True)
class EntityDetailReadModel:
    lookup_name: str
    matched_names: list[str]
    observation_count: int
    latest_reporting_period: date | None
    disclosure_completeness_counts: dict[str, int]
    canonical_asset_class_counts: dict[str, int]
    observations: list[EntityObservationReadModel]


def list_source_files(session: Session) -> list[SourceFileListItem]:
    rows = session.execute(
        select(
            SourceFile.id,
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            SourceFile.adapter_key,
            SourceFile.schema_fingerprint,
            SourceFile.mapping_version_id,
            SourceFile.ingest_status,
            ReportingPeriod.period_end_date,
            SourceFile.received_at,
            SourceFile.encoding_replacement_count,
            SourceFile.version_number,
            SourceFile.is_current_version,
            func.count(Holding.id).label("rows_loaded"),
        )
        .join(Fund, Fund.id == SourceFile.fund_id)
        .outerjoin(ReportingPeriod, ReportingPeriod.id == SourceFile.reporting_period_id)
        .outerjoin(Holding, Holding.source_file_id == SourceFile.id)
        .group_by(
            SourceFile.id,
            Fund.code,
            Fund.name,
            SourceFile.adapter_key,
            SourceFile.schema_fingerprint,
            SourceFile.mapping_version_id,
            SourceFile.ingest_status,
            ReportingPeriod.period_end_date,
            SourceFile.received_at,
            SourceFile.encoding_replacement_count,
            SourceFile.version_number,
            SourceFile.is_current_version,
        )
        .order_by(SourceFile.received_at.desc(), SourceFile.id.desc())
    ).all()
    return [
        SourceFileListItem(
            id=row.id,
            fund_code=row.fund_code,
            fund_name=row.fund_name,
            adapter_key=row.adapter_key,
            schema_fingerprint=row.schema_fingerprint,
            mapping_version_id=row.mapping_version_id,
            ingest_status=row.ingest_status,
            period_end_date=row.period_end_date,
            received_at=row.received_at,
            encoding_replacement_count=row.encoding_replacement_count,
            rows_loaded=int(row.rows_loaded),
            version_number=row.version_number,
            is_current_version=row.is_current_version,
        )
        for row in rows
    ]


def get_source_file_detail(
    session: Session,
    *,
    source_file_id: int,
    page: int = 1,
    size: int = 50,
) -> SourceFileDetailReadModel | None:
    source_file_row = session.execute(
        select(
            SourceFile.id,
            SourceFile.fund_id,
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            SourceFile.investment_option_id,
            InvestmentOption.source_option_name.label("investment_option_name"),
            SourceFile.adapter_key,
            SourceFile.source_url,
            SourceFile.checksum,
            SourceFile.ingest_status,
            SourceFile.schema_fingerprint,
            SourceFile.mapping_version_id,
            SourceFile.reporting_period_id,
            ReportingPeriod.period_end_date.label("reporting_period_end_date"),
            SourceFile.publication_date,
            SourceFile.terms_snapshot_url,
            SourceFile.downloaded_at,
            SourceFile.received_at,
            SourceFile.encoding_replacement_count,
            SourceFile.version_number,
            SourceFile.is_current_version,
            SourceFile.supersedes_source_file_id,
        )
        .join(Fund, Fund.id == SourceFile.fund_id)
        .outerjoin(InvestmentOption, InvestmentOption.id == SourceFile.investment_option_id)
        .outerjoin(ReportingPeriod, ReportingPeriod.id == SourceFile.reporting_period_id)
        .where(SourceFile.id == source_file_id)
    ).one_or_none()
    if source_file_row is None:
        return None

    source_file = SourceFileSummary(
        id=source_file_row.id,
        fund_id=source_file_row.fund_id,
        fund_code=source_file_row.fund_code,
        fund_name=source_file_row.fund_name,
        investment_option_id=source_file_row.investment_option_id,
        investment_option_name=source_file_row.investment_option_name,
        adapter_key=source_file_row.adapter_key,
        source_url=source_file_row.source_url,
        checksum=source_file_row.checksum,
        ingest_status=source_file_row.ingest_status,
        schema_fingerprint=source_file_row.schema_fingerprint,
        mapping_version_id=source_file_row.mapping_version_id,
        reporting_period_id=source_file_row.reporting_period_id,
        reporting_period_end_date=source_file_row.reporting_period_end_date,
        publication_date=source_file_row.publication_date,
        terms_snapshot_url=source_file_row.terms_snapshot_url,
        downloaded_at=source_file_row.downloaded_at,
        received_at=source_file_row.received_at,
        encoding_replacement_count=source_file_row.encoding_replacement_count,
        version_number=source_file_row.version_number,
        is_current_version=source_file_row.is_current_version,
        supersedes_source_file_id=source_file_row.supersedes_source_file_id,
    )

    disclosure_counts = [
        (row[0], int(row[1]))
        for row in session.execute(
            select(Holding.disclosure_completeness, func.count(Holding.id))
            .where(Holding.source_file_id == source_file_id)
            .group_by(Holding.disclosure_completeness)
            .order_by(Holding.disclosure_completeness)
        ).all()
    ]
    canonical_asset_class_counts = [
        (row[0], int(row[1]))
        for row in session.execute(
            select(CanonicalAssetClass.code, func.count(Holding.id))
            .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
            .where(Holding.source_file_id == source_file_id)
            .group_by(CanonicalAssetClass.code)
            .order_by(CanonicalAssetClass.code)
        ).all()
    ]

    total_rows = session.scalar(select(func.count(Holding.id)).where(Holding.source_file_id == source_file_id)) or 0
    total_pages = max(1, math.ceil(total_rows / size))
    offset = (page - 1) * size

    holding_rows = session.execute(
        select(
            InvestmentOption.source_option_code.label("source_option_code"),
            InvestmentOption.source_option_name.label("source_option_name"),
            Holding.source_row_number,
            Holding.raw_name,
            Holding.source_asset_class_raw,
            Holding.source_subclass_raw,
            CanonicalAssetClass.code.label("canonical_asset_class_code"),
            Holding.disclosure_completeness,
            Holding.is_aggregate,
            Holding.value_aud,
            Holding.ownership_pct,
            Holding.currency_raw,
            Holding.security_identifier_type,
            Holding.security_identifier_value,
            Holding.value_band_raw,
            Holding.raw_payload_json,
            Holding.metadata_attached_from_row_numbers,
            Holding.ingested_at,
        )
        .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .where(Holding.source_file_id == source_file_id)
        .order_by(Holding.source_row_number.asc(), Holding.id.asc())
        .offset(offset)
        .limit(size)
    ).all()

    holdings = []
    for row in holding_rows:
        metadata_attached_from_row_numbers = list(row.metadata_attached_from_row_numbers or [])
        holdings.append(
            SourceFileHoldingRow(
                source_option_code=row.source_option_code,
                source_option_name=row.source_option_name,
                source_row_number=row.source_row_number,
                raw_name=row.raw_name,
                source_asset_class_raw=row.source_asset_class_raw,
                source_subclass_raw=row.source_subclass_raw,
                canonical_asset_class_code=row.canonical_asset_class_code,
                disclosure_completeness=row.disclosure_completeness,
                is_aggregate=row.is_aggregate,
                value_aud=row.value_aud,
                ownership_pct=row.ownership_pct,
                currency_raw=row.currency_raw,
                security_identifier_type=row.security_identifier_type,
                security_identifier_value=row.security_identifier_value,
                value_band_raw=row.value_band_raw,
                raw_payload_json=_normalise_raw_payload_entries(
                    row.raw_payload_json,
                    source_row_number=row.source_row_number,
                    metadata_attached_from_row_numbers=metadata_attached_from_row_numbers,
                ),
                metadata_attached_from_row_numbers=metadata_attached_from_row_numbers,
                ingested_at=row.ingested_at,
            )
        )

    return SourceFileDetailReadModel(
        source_file=source_file,
        disclosure_counts=disclosure_counts,
        canonical_asset_class_counts=canonical_asset_class_counts,
        holdings=holdings,
        page=page,
        size=size,
        total_rows=total_rows,
        total_pages=total_pages,
    )


def _normalise_raw_payload_entries(
    raw_payload_json: object,
    *,
    source_row_number: int,
    metadata_attached_from_row_numbers: list[int],
) -> list[dict[str, object]]:
    if raw_payload_json is None:
        return []

    if not isinstance(raw_payload_json, list):
        return [_tagged_payload_entry(source_row_number, raw_payload_json)]

    if not raw_payload_json:
        return []

    first_item = raw_payload_json[0]
    if isinstance(first_item, dict):
        return [
            _tagged_payload_entry(
                int(item.get("source_row_number", source_row_number)) if isinstance(item, dict) else source_row_number,
                item.get("payload", []) if isinstance(item, dict) else item,
            )
            for item in raw_payload_json
        ]

    if isinstance(first_item, list):
        source_row_numbers = [source_row_number, *metadata_attached_from_row_numbers]
        entries: list[dict[str, object]] = []
        for index, payload in enumerate(raw_payload_json):
            tagged_row_number = source_row_numbers[index] if index < len(source_row_numbers) else source_row_number
            entries.append(_tagged_payload_entry(tagged_row_number, payload))
        return entries

    return [_tagged_payload_entry(source_row_number, raw_payload_json)]


def _tagged_payload_entry(source_row_number: int, payload: object) -> dict[str, object]:
    if isinstance(payload, list):
        normalised_payload: object = list(payload)
    else:
        normalised_payload = payload
    return {
        "source_row_number": source_row_number,
        "payload": normalised_payload,
    }


def get_entity_detail_by_name(session: Session, *, name: str) -> EntityDetailReadModel | None:
    lookup_name = name.strip()
    if lookup_name == "":
        raise ValueError("name must not be blank")

    rows = session.execute(
        select(
            Holding.raw_name,
            Holding.source_file_id,
            Holding.source_row_number,
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            InvestmentOption.source_option_name.label("option_name"),
            ReportingPeriod.period_end_date.label("reporting_period_end_date"),
            CanonicalAssetClass.code.label("canonical_asset_class_code"),
            Holding.source_asset_class_raw,
            Holding.source_subclass_raw,
            Holding.disclosure_completeness,
            Holding.value_aud,
            Holding.ownership_pct,
            Holding.units,
            Holding.value_band_raw,
            Holding.currency_raw,
            Holding.security_identifier_type,
            Holding.security_identifier_value,
        )
        .join(Fund, Fund.id == Holding.source_fund_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
        .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
        .where(
            Holding.is_aggregate.is_(False),
            Holding.raw_name.is_not(None),
            func.lower(Holding.raw_name) == lookup_name.casefold(),
        )
        .order_by(
            ReportingPeriod.period_end_date.desc(),
            Fund.code.asc(),
            InvestmentOption.source_option_name.asc(),
            Holding.source_row_number.asc(),
        )
    ).all()
    if not rows:
        return None

    observations = [
        EntityObservationReadModel(
            raw_name=row.raw_name,
            source_file_id=row.source_file_id,
            source_row_number=row.source_row_number,
            fund_code=row.fund_code,
            fund_name=row.fund_name,
            option_name=row.option_name,
            reporting_period_end_date=row.reporting_period_end_date,
            canonical_asset_class_code=row.canonical_asset_class_code,
            source_asset_class_raw=row.source_asset_class_raw,
            source_subclass_raw=row.source_subclass_raw,
            disclosure_completeness=row.disclosure_completeness,
            value_aud=row.value_aud,
            ownership_pct=row.ownership_pct,
            units=row.units,
            value_band_raw=row.value_band_raw,
            currency_raw=row.currency_raw,
            security_identifier_type=row.security_identifier_type,
            security_identifier_value=row.security_identifier_value,
        )
        for row in rows
    ]

    disclosure_counts = Counter(observation.disclosure_completeness for observation in observations)
    asset_class_counts = Counter(observation.canonical_asset_class_code for observation in observations)
    latest_reporting_period = max(observation.reporting_period_end_date for observation in observations)

    return EntityDetailReadModel(
        lookup_name=lookup_name,
        matched_names=sorted({observation.raw_name for observation in observations}),
        observation_count=len(observations),
        latest_reporting_period=latest_reporting_period,
        disclosure_completeness_counts=dict(sorted(disclosure_counts.items())),
        canonical_asset_class_counts=dict(sorted(asset_class_counts.items())),
        observations=observations,
    )
