from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.base import AdapterParseResult, SourceFileMetadata
from adapters.hesta import HestaPhdAdapter
from app.db.models import (
    CANONICAL_ASSET_CLASS_SEED,
    CanonicalAssetClass,
    Fund,
    Holding,
    InvestmentOption,
    ReportingPeriod,
    SourceFile,
)


class LoaderError(Exception):
    """Base Stage 1 load error."""


class ReportingPeriodMismatchError(LoaderError):
    pass


class SourceFileNotFoundError(LoaderError):
    pass


class CanonicalAssetClassMissingError(LoaderError):
    pass


@dataclass(frozen=True)
class LoadSummary:
    source_file_id: int
    reporting_period_id: int
    investment_option_id: int
    rows_staged: int
    rows_inserted: int
    rows_skipped_existing: int
    schema_fingerprint: str
    warnings: list[str]


def seed_canonical_asset_classes(session: Session) -> None:
    existing_codes = set(session.scalars(select(CanonicalAssetClass.code)).all())
    for row in CANONICAL_ASSET_CLASS_SEED:
        if row["code"] in existing_codes:
            continue
        session.add(CanonicalAssetClass(**row))
    session.flush()


def register_source_file(
    session: Session,
    *,
    fund_code: str,
    fund_name: str,
    adapter_key: str,
    source_url: str,
    checksum: str,
    received_at: datetime,
    reporting_period_id: int | None = None,
    publication_date: date | None = None,
) -> SourceFileMetadata:
    fund = session.scalar(select(Fund).where(Fund.code == fund_code))
    if fund is None:
        fund = Fund(code=fund_code, name=fund_name)
        session.add(fund)
        session.flush()

    existing = session.scalar(
        select(SourceFile).where(
            SourceFile.fund_id == fund.id,
            SourceFile.adapter_key == adapter_key,
            SourceFile.checksum == checksum,
            SourceFile.is_current_version.is_(True),
        )
    )
    if existing is None:
        existing = SourceFile(
            fund_id=fund.id,
            adapter_key=adapter_key,
            source_url=source_url,
            checksum=checksum,
            reporting_period_id=reporting_period_id,
            ingest_status="registered",
            publication_date=publication_date,
            version_number=1,
            is_current_version=True,
            encoding_replacement_count=0,
            received_at=received_at,
        )
        session.add(existing)
        session.flush()

    return SourceFileMetadata(
        source_file_id=existing.id,
        fund_id=fund.id,
        suspected_adapter_key=adapter_key,
        reporting_period_id=existing.reporting_period_id,
        source_url=existing.source_url,
        checksum=existing.checksum,
        received_at=existing.received_at,
    )


def get_or_create_reporting_period(session: Session, period_end_date: date) -> ReportingPeriod:
    period = session.scalar(select(ReportingPeriod).where(ReportingPeriod.period_end_date == period_end_date))
    if period is not None:
        return period
    period = ReportingPeriod(
        period_end_date=period_end_date,
        disclosure_due_date=period_end_date + timedelta(days=90),
        label=period_end_date.isoformat(),
        source_cycle="semi_annual",
    )
    session.add(period)
    session.flush()
    return period


def get_or_create_investment_option(
    session: Session,
    *,
    fund_id: int,
    source_option_code: str,
    source_option_name: str,
    reporting_period_date: date,
) -> InvestmentOption:
    option = session.scalar(
        select(InvestmentOption).where(
            InvestmentOption.fund_id == fund_id,
            InvestmentOption.source_option_code == source_option_code,
        )
    )
    if option is not None:
        return option
    option = InvestmentOption(
        fund_id=fund_id,
        source_option_code=source_option_code,
        source_option_name=source_option_name,
        canonical_option_name=source_option_name,
        active_from_period=reporting_period_date,
        active_to_period=None,
    )
    session.add(option)
    session.flush()
    return option


def load_adapter_parse_result(
    session: Session,
    metadata: SourceFileMetadata,
    parse_result: AdapterParseResult,
) -> LoadSummary:
    source_file = session.get(SourceFile, metadata.source_file_id)
    if source_file is None:
        raise SourceFileNotFoundError(f"Source file {metadata.source_file_id!r} was not registered")

    seed_canonical_asset_classes(session)

    observed_dates = parse_result.structural_metadata["observed_reporting_dates"]
    observed_date = date.fromisoformat(_normalise_observed_date(observed_dates[0]))

    if source_file.reporting_period_id is None:
        reporting_period = get_or_create_reporting_period(session, observed_date)
        source_file.reporting_period_id = reporting_period.id
    else:
        reporting_period = session.get(ReportingPeriod, source_file.reporting_period_id)
        if reporting_period is None:
            raise ReportingPeriodMismatchError(
                f"Registered reporting period {source_file.reporting_period_id!r} does not exist"
            )
        if reporting_period.period_end_date != observed_date:
            raise ReportingPeriodMismatchError(
                f"Registered reporting period {reporting_period.period_end_date} does not match parsed date {observed_date}"
            )

    observed_options = parse_result.structural_metadata["observed_options"]
    option = get_or_create_investment_option(
        session,
        fund_id=source_file.fund_id,
        source_option_code=observed_options[0],
        source_option_name=observed_options[0],
        reporting_period_date=reporting_period.period_end_date,
    )
    if source_file.investment_option_id is None:
        source_file.investment_option_id = option.id
    elif source_file.investment_option_id != option.id:
        raise LoaderError(
            f"Registered source file option {source_file.investment_option_id!r} does not match parsed option {option.id!r}"
        )

    source_file.schema_fingerprint = parse_result.schema_fingerprint
    source_file.encoding_replacement_count = int(parse_result.structural_metadata["encoding_replacement_count"])
    source_file.ingest_status = "loading"

    asset_class_map = {
        asset_class.code: asset_class.id
        for asset_class in session.scalars(select(CanonicalAssetClass)).all()
    }

    staged_rows: list[dict[str, object]] = []
    for record in parse_result.holdings:
        if record.reporting_period_date != reporting_period.period_end_date:
            raise ReportingPeriodMismatchError(
                f"Parsed row date {record.reporting_period_date} does not match reporting period {reporting_period.period_end_date}"
            )
        canonical_asset_class_id = asset_class_map.get(record.canonical_asset_class_code)
        if canonical_asset_class_id is None:
            raise CanonicalAssetClassMissingError(record.canonical_asset_class_code)
        staged_rows.append(
            {
                "source_file_id": source_file.id,
                "source_fund_id": source_file.fund_id,
                "source_option_id": option.id,
                "reporting_period_id": reporting_period.id,
                "entity_id": None,
                "raw_name": record.raw_name,
                "value_aud": record.value_aud,
                "ownership_pct": record.ownership_pct,
                "units": record.units,
                "is_aggregate": record.is_aggregate,
                "disclosure_completeness": record.disclosure_completeness,
                "canonical_asset_class_id": canonical_asset_class_id,
                "source_asset_class_raw": record.source_asset_class_raw,
                "source_subclass_raw": record.source_subclass_raw,
                "address": record.address_raw,
                "geo_lat": record.geo_lat,
                "geo_lng": record.geo_lng,
                "security_identifier_value": record.security_identifier_value,
                "security_identifier_type": record.security_identifier_type,
                "value_band_raw": record.value_band_raw,
                "source_row_hash": record.source_row_hash,
                "source_row_number": record.source_row_number,
                "raw_payload_json": record.raw_payload_json,
                "manager_entity_id": None,
                "issuer_entity_id": None,
                "currency_raw": record.currency_raw,
                "classification_raw": record.classification_raw,
                "location_raw": record.location_raw,
                "parse_warning_flags": record.parse_warning_flags,
                "metadata_attached_from_row_numbers": record.metadata_attached_from_row_numbers,
            }
        )

    existing_hashes = set(
        session.scalars(
            select(Holding.source_row_hash).where(Holding.source_file_id == source_file.id)
        ).all()
    )

    rows_inserted = 0
    rows_skipped_existing = 0
    for staged in staged_rows:
        if staged["source_row_hash"] in existing_hashes:
            rows_skipped_existing += 1
            continue
        session.add(Holding(**staged))
        existing_hashes.add(staged["source_row_hash"])
        rows_inserted += 1

    source_file.ingest_status = "loaded"
    session.flush()

    return LoadSummary(
        source_file_id=source_file.id,
        reporting_period_id=reporting_period.id,
        investment_option_id=option.id,
        rows_staged=len(staged_rows),
        rows_inserted=rows_inserted,
        rows_skipped_existing=rows_skipped_existing,
        schema_fingerprint=parse_result.schema_fingerprint,
        warnings=parse_result.adapter_warnings,
    )


def ingest_hesta_local_file(
    session: Session,
    *,
    fund_code: str,
    fund_name: str,
    file_path: str,
    publication_date: date | None = None,
    reporting_period_id: int | None = None,
    received_at: datetime | None = None,
) -> LoadSummary:
    file_path_obj = Path(file_path)
    raw_bytes = file_path_obj.read_bytes()
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    metadata = register_source_file(
        session,
        fund_code=fund_code,
        fund_name=fund_name,
        adapter_key="HestaPhdAdapter",
        source_url=str(file_path_obj),
        checksum=checksum,
        received_at=received_at or datetime.utcnow(),
        reporting_period_id=reporting_period_id,
        publication_date=publication_date,
    )
    parse_result = HestaPhdAdapter().parse(metadata, raw_bytes)
    return load_adapter_parse_result(session, metadata, parse_result)


def _normalise_observed_date(observed_date: str) -> str:
    if "-" in observed_date:
        return observed_date
    return datetime.strptime(observed_date, "%d/%m/%Y").date().isoformat()

