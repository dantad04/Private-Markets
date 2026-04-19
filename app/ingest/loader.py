from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.art_qsuper import ArtQsuperPhdAdapter
from adapters.art_sunsuper import ArtSunsuperPhdAdapter
from adapters.art_qsuper_errors import ArtQsuperAdapterError
from adapters.aware import AwarePhdAdapter
from adapters.aware_errors import AwareAdapterError
from adapters.base import AdapterParseResult, SourceFileMetadata
from adapters.hesta import HestaPhdAdapter
from adapters.hostplus import HostPlusPhdStateMachineAdapter
from adapters.hostplus_errors import HostPlusAdapterError
from adapters.sunsuper_schema_errors import SunsuperSchemaAdapterError
from adapters.unisuper import UniSuperPhdStateMachineAdapter
from adapters.unisuper_errors import UniSuperAdapterError
from app.db.models import (
    CANONICAL_ASSET_CLASS_SEED,
    CanonicalAssetClass,
    Fund,
    Holding,
    InvestmentOption,
    ReportingPeriod,
    SourceFile,
)
from app.ingest.governance import (
    SchemaDriftDetectedError,
    UnapprovedTaxonomyMappingError,
    create_schema_review_queue_item,
    enforce_approved_mapping,
    ensure_approved_mapping_seeded,
)


class LoaderError(Exception):
    """Base Stage 1 load error."""


class ReportingPeriodMismatchError(LoaderError):
    pass


class SourceFileNotFoundError(LoaderError):
    pass


class CanonicalAssetClassMissingError(LoaderError):
    pass


class ActiveSourceFileConflictError(LoaderError):
    pass


class MissingReportingPeriodRegistrationError(LoaderError):
    pass


@dataclass(frozen=True)
class LoadSummary:
    source_file_id: int
    reporting_period_id: int
    investment_option_id: int | None
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
    terms_snapshot_url: str | None = None,
    downloaded_at: datetime | None = None,
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
            terms_snapshot_url=terms_snapshot_url,
            downloaded_at=downloaded_at,
            encoding_replacement_count=0,
            received_at=received_at,
        )
        session.add(existing)
        session.flush()

    reporting_period_end_date = None
    if existing.reporting_period_id is not None:
        reporting_period = session.get(ReportingPeriod, existing.reporting_period_id)
        if reporting_period is not None:
            reporting_period_end_date = reporting_period.period_end_date

    return SourceFileMetadata(
        source_file_id=existing.id,
        fund_id=fund.id,
        suspected_adapter_key=adapter_key,
        reporting_period_id=existing.reporting_period_id,
        source_url=existing.source_url,
        checksum=existing.checksum,
        received_at=existing.received_at,
        reporting_period_end_date=reporting_period_end_date,
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


def activate_source_file_version(
    session: Session,
    *,
    source_file: SourceFile,
    investment_option_id: int | None,
    reporting_period_id: int,
) -> None:
    where_clauses = [
        SourceFile.fund_id == source_file.fund_id,
        SourceFile.reporting_period_id == reporting_period_id,
        SourceFile.adapter_key == source_file.adapter_key,
    ]
    if investment_option_id is None:
        where_clauses.append(SourceFile.investment_option_id.is_(None))
    else:
        where_clauses.append(SourceFile.investment_option_id == investment_option_id)

    related_versions = session.scalars(
        select(SourceFile).where(*where_clauses).order_by(SourceFile.version_number.desc(), SourceFile.id.desc())
    ).all()

    active_versions = [row for row in related_versions if row.is_current_version and row.id != source_file.id]
    if len(active_versions) > 1:
        raise ActiveSourceFileConflictError(
            "Multiple active source files exist for the same fund/option/reporting-period/adapter slice"
        )

    prior_versions = [row for row in related_versions if row.id != source_file.id]
    max_prior_version_number = max((row.version_number for row in prior_versions), default=0)
    source_file.is_current_version = True
    source_file.superseded_at = None
    source_file.supersession_reason = None

    if not prior_versions:
        source_file.version_number = 1
        source_file.supersedes_source_file_id = None
        return

    active_prior = active_versions[0] if active_versions else None
    if active_prior is None:
        source_file.version_number = max_prior_version_number + 1
        source_file.supersedes_source_file_id = None
        return

    source_file.is_current_version = False
    active_prior.is_current_version = False
    active_prior.superseded_at = datetime.now(UTC)
    active_prior.supersession_reason = f"Superseded by source_file_id={source_file.id}"
    session.flush()

    source_file.version_number = active_prior.version_number + 1
    source_file.supersedes_source_file_id = active_prior.id
    source_file.is_current_version = True


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
    option_names_by_code: dict[str, str] = {}
    for record in parse_result.holdings:
        option_names_by_code.setdefault(record.source_option_code, record.source_option_name_raw)

    option_ids_by_code: dict[str, int] = {}
    for option_code in observed_options:
        option_name = option_names_by_code.get(option_code, option_code)
        option = get_or_create_investment_option(
            session,
            fund_id=source_file.fund_id,
            source_option_code=option_code,
            source_option_name=option_name,
            reporting_period_date=reporting_period.period_end_date,
        )
        option_ids_by_code[option_code] = option.id

    active_version_option_id: int | None
    if len(observed_options) == 1:
        option_id = option_ids_by_code[observed_options[0]]
        if source_file.investment_option_id is None:
            source_file.investment_option_id = option_id
        elif source_file.investment_option_id != option_id:
            raise LoaderError(
                f"Registered source file option {source_file.investment_option_id!r} does not match parsed option {option_id!r}"
            )
        active_version_option_id = option_id
    else:
        source_file.investment_option_id = None
        active_version_option_id = None

    activate_source_file_version(
        session,
        source_file=source_file,
        investment_option_id=active_version_option_id,
        reporting_period_id=reporting_period.id,
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
                "source_option_id": option_ids_by_code[record.source_option_code],
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
        investment_option_id=source_file.investment_option_id,
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
        received_at=received_at or datetime.now(UTC),
        reporting_period_id=reporting_period_id,
        publication_date=publication_date,
    )
    parse_result = HestaPhdAdapter().parse(metadata, raw_bytes)
    return load_adapter_parse_result(session, metadata, parse_result)


def ingest_aware_local_file(
    session: Session,
    *,
    fund_code: str,
    fund_name: str,
    file_path: str,
    publication_date: date | None = None,
    reporting_period_id: int | None = None,
    received_at: datetime | None = None,
    terms_snapshot_url: str | None = None,
    downloaded_at: datetime | None = None,
) -> LoadSummary:
    file_path_obj = Path(file_path)
    raw_bytes = file_path_obj.read_bytes()
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    metadata = register_source_file(
        session,
        fund_code=fund_code,
        fund_name=fund_name,
        adapter_key="AwarePhdAdapter",
        source_url=str(file_path_obj),
        checksum=checksum,
        received_at=received_at or datetime.now(UTC),
        reporting_period_id=reporting_period_id,
        publication_date=publication_date,
        terms_snapshot_url=terms_snapshot_url,
        downloaded_at=downloaded_at,
    )
    source_file = session.get(SourceFile, metadata.source_file_id)
    try:
        ensure_approved_mapping_seeded(session, adapter_key="AwarePhdAdapter")
        parse_result = AwarePhdAdapter().parse(metadata, raw_bytes)
        enforce_approved_mapping(
            session,
            source_file=source_file,
            parse_result=parse_result,
            raw_bytes=raw_bytes,
            source_section_raw="ASSETS",
        )
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError):
        session.flush()
        raise
    except AwareAdapterError as exc:
        source_file.ingest_status = "review_required"
        approved_mapping_version_id = None
        try:
            approved_mapping_version_id = ensure_approved_mapping_seeded(session, adapter_key="AwarePhdAdapter").id
        except Exception:
            approved_mapping_version_id = None
        create_schema_review_queue_item(
            session,
            source_file=source_file,
            approved_mapping_version_id=approved_mapping_version_id,
            review_reason="adapter_parse_failure",
            observed_schema_fingerprint=None,
            drift_summary_json={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            raw_bytes=raw_bytes,
        )
        session.flush()
        raise
    return load_adapter_parse_result(session, metadata, parse_result)


def ingest_art_qsuper_local_file(
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
        adapter_key="ArtQsuperPhdAdapter",
        source_url=str(file_path_obj),
        checksum=checksum,
        received_at=received_at or datetime.now(UTC),
        reporting_period_id=reporting_period_id,
        publication_date=publication_date,
    )
    source_file = session.get(SourceFile, metadata.source_file_id)
    try:
        ensure_approved_mapping_seeded(session, adapter_key="ArtQsuperPhdAdapter")
        parse_result = ArtQsuperPhdAdapter().parse(metadata, raw_bytes)
        enforce_approved_mapping(
            session,
            source_file=source_file,
            parse_result=parse_result,
            raw_bytes=raw_bytes,
            source_section_raw=None,
        )
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError):
        session.flush()
        raise
    except ArtQsuperAdapterError as exc:
        source_file.ingest_status = "review_required"
        approved_mapping_version_id = None
        try:
            approved_mapping_version_id = ensure_approved_mapping_seeded(session, adapter_key="ArtQsuperPhdAdapter").id
        except Exception:
            approved_mapping_version_id = None
        create_schema_review_queue_item(
            session,
            source_file=source_file,
            approved_mapping_version_id=approved_mapping_version_id,
            review_reason="adapter_parse_failure",
            observed_schema_fingerprint=None,
            drift_summary_json={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            raw_bytes=raw_bytes,
        )
        session.flush()
        raise
    return load_adapter_parse_result(session, metadata, parse_result)


def ingest_art_sunsuper_local_file(
    session: Session,
    *,
    fund_code: str,
    fund_name: str,
    file_path: str,
    reporting_period_id: int | None,
    publication_date: date | None = None,
    received_at: datetime | None = None,
) -> LoadSummary:
    if reporting_period_id is None:
        raise MissingReportingPeriodRegistrationError(
            "Sunsuper-schema files require reporting_period_id because the row schema has no reporting date column"
        )

    file_path_obj = Path(file_path)
    raw_bytes = file_path_obj.read_bytes()
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    metadata = register_source_file(
        session,
        fund_code=fund_code,
        fund_name=fund_name,
        adapter_key="ArtSunsuperPhdAdapter",
        source_url=str(file_path_obj),
        checksum=checksum,
        received_at=received_at or datetime.now(UTC),
        reporting_period_id=reporting_period_id,
        publication_date=publication_date,
    )
    if metadata.reporting_period_end_date is None:
        raise MissingReportingPeriodRegistrationError(
            f"Registered reporting period {reporting_period_id!r} does not exist"
        )

    source_file = session.get(SourceFile, metadata.source_file_id)
    try:
        ensure_approved_mapping_seeded(session, adapter_key="ArtSunsuperPhdAdapter")
        parse_result = ArtSunsuperPhdAdapter().parse(metadata, raw_bytes)
        approved_mapping_version_id = enforce_approved_mapping(
            session,
            source_file=source_file,
            parse_result=parse_result,
            raw_bytes=raw_bytes,
            source_section_raw=None,
        )
        review_events = list(parse_result.structural_metadata.get("review_queue_events", []))
        for event in review_events:
            create_schema_review_queue_item(
                session,
                source_file=source_file,
                approved_mapping_version_id=approved_mapping_version_id,
                review_reason=str(event.get("review_reason", "adapter_review")),
                observed_schema_fingerprint=parse_result.schema_fingerprint,
                drift_summary_json=dict(event.get("details", {})),
                raw_bytes=raw_bytes,
            )
        if review_events:
            session.flush()
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError):
        session.flush()
        raise
    except SunsuperSchemaAdapterError as exc:
        source_file.ingest_status = "review_required"
        approved_mapping_version_id = None
        try:
            approved_mapping_version_id = ensure_approved_mapping_seeded(session, adapter_key="ArtSunsuperPhdAdapter").id
        except Exception:
            approved_mapping_version_id = None
        create_schema_review_queue_item(
            session,
            source_file=source_file,
            approved_mapping_version_id=approved_mapping_version_id,
            review_reason="adapter_parse_failure",
            observed_schema_fingerprint=None,
            drift_summary_json={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            raw_bytes=raw_bytes,
        )
        session.flush()
        raise
    return load_adapter_parse_result(session, metadata, parse_result)


def ingest_unisuper_local_file(
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
        adapter_key="UniSuperPhdStateMachineAdapter",
        source_url=str(file_path_obj),
        checksum=checksum,
        received_at=received_at or datetime.now(UTC),
        reporting_period_id=reporting_period_id,
        publication_date=publication_date,
    )
    if metadata.reporting_period_end_date is None:
        raise MissingReportingPeriodRegistrationError(
            f"Registered reporting period {reporting_period_id!r} does not exist"
        )

    source_file = session.get(SourceFile, metadata.source_file_id)
    try:
        ensure_approved_mapping_seeded(session, adapter_key="UniSuperPhdStateMachineAdapter")
        parse_result = UniSuperPhdStateMachineAdapter().parse(metadata, raw_bytes)
        approved_mapping_version_id = enforce_approved_mapping(
            session,
            source_file=source_file,
            parse_result=parse_result,
            raw_bytes=raw_bytes,
            source_section_raw=None,
        )
        review_events = list(parse_result.structural_metadata.get("review_queue_events", []))
        for event in review_events:
            create_schema_review_queue_item(
                session,
                source_file=source_file,
                approved_mapping_version_id=approved_mapping_version_id,
                review_reason=str(event.get("review_reason", "adapter_review")),
                observed_schema_fingerprint=parse_result.schema_fingerprint,
                drift_summary_json=dict(event.get("details", {})),
                raw_bytes=raw_bytes,
            )
        if review_events:
            session.flush()
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError):
        session.flush()
        raise
    except UniSuperAdapterError as exc:
        source_file.ingest_status = "review_required"
        approved_mapping_version_id = None
        try:
            approved_mapping_version_id = ensure_approved_mapping_seeded(
                session, adapter_key="UniSuperPhdStateMachineAdapter"
            ).id
        except Exception:
            approved_mapping_version_id = None
        create_schema_review_queue_item(
            session,
            source_file=source_file,
            approved_mapping_version_id=approved_mapping_version_id,
            review_reason="adapter_parse_failure",
            observed_schema_fingerprint=None,
            drift_summary_json={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            raw_bytes=raw_bytes,
        )
        session.flush()
        raise
    return load_adapter_parse_result(session, metadata, parse_result)


def ingest_hostplus_local_file(
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
        adapter_key="HostPlusPhdStateMachineAdapter",
        source_url=str(file_path_obj),
        checksum=checksum,
        received_at=received_at or datetime.now(UTC),
        reporting_period_id=reporting_period_id,
        publication_date=publication_date,
    )
    if metadata.reporting_period_end_date is None:
        raise MissingReportingPeriodRegistrationError(
            f"Registered reporting period {reporting_period_id!r} does not exist"
        )

    source_file = session.get(SourceFile, metadata.source_file_id)
    try:
        ensure_approved_mapping_seeded(session, adapter_key="HostPlusPhdStateMachineAdapter")
        parse_result = HostPlusPhdStateMachineAdapter().parse(metadata, raw_bytes)
        approved_mapping_version_id = enforce_approved_mapping(
            session,
            source_file=source_file,
            parse_result=parse_result,
            raw_bytes=raw_bytes,
            source_section_raw=None,
        )
        review_events = list(parse_result.structural_metadata.get("review_queue_events", []))
        for event in review_events:
            create_schema_review_queue_item(
                session,
                source_file=source_file,
                approved_mapping_version_id=approved_mapping_version_id,
                review_reason=str(event.get("review_reason", "adapter_review")),
                observed_schema_fingerprint=parse_result.schema_fingerprint,
                drift_summary_json=dict(event.get("details", {})),
                raw_bytes=raw_bytes,
            )
        if review_events:
            session.flush()
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError):
        session.flush()
        raise
    except HostPlusAdapterError as exc:
        source_file.ingest_status = "review_required"
        approved_mapping_version_id = None
        try:
            approved_mapping_version_id = ensure_approved_mapping_seeded(
                session, adapter_key="HostPlusPhdStateMachineAdapter"
            ).id
        except Exception:
            approved_mapping_version_id = None
        create_schema_review_queue_item(
            session,
            source_file=source_file,
            approved_mapping_version_id=approved_mapping_version_id,
            review_reason="adapter_parse_failure",
            observed_schema_fingerprint=None,
            drift_summary_json={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            raw_bytes=raw_bytes,
        )
        session.flush()
        raise
    return load_adapter_parse_result(session, metadata, parse_result)


def _normalise_observed_date(observed_date: str) -> str:
    if "-" in observed_date:
        return observed_date
    if "/" in observed_date:
        return datetime.strptime(observed_date, "%d/%m/%Y").date().isoformat()
    return datetime.strptime(observed_date, "%d %B %Y").date().isoformat()
