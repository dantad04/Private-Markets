from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import (
    AdapterMappingVersion,
    CanonicalAssetClass,
    Entity,
    EntityAlias,
    EntityRelationship,
    EntityResolutionQueue,
    Fund,
    Holding,
    InvestmentOption,
    ReportingPeriod,
    SchemaReviewQueue,
    SourceFile,
)


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


@dataclass(frozen=True)
class CrossAdapterObservationReadModel:
    normalized_name: str
    raw_name: str
    source_file_id: int
    fund_code: str
    fund_name: str
    option_code: str
    option_name: str
    reporting_period_end_date: date
    disclosure_completeness: str
    value_aud: Decimal | None
    ownership_pct: Decimal | None
    value_band_raw: str | None
    is_aggregate: bool


@dataclass(frozen=True)
class CrossAdapterHoldingsReadModel:
    entity_id: int | None
    lookup_name: str
    normalized_lookup_name: str
    matched_normalized_names: list[str]
    matched_raw_names: list[str]
    observation_count: int
    fund_count: int
    observations: list[CrossAdapterObservationReadModel]


@dataclass(frozen=True)
class EntityRelationshipReadModel:
    relationship_id: int
    from_entity_id: int
    to_entity_id: int
    relationship_type: str
    source: str
    notes: str | None


@dataclass(frozen=True)
class EntityObservedHoldingsCountReadModel:
    fund_code: str
    fund_name: str
    reporting_period_end_date: date
    observation_count: int


@dataclass(frozen=True)
class CanonicalEntityDetailReadModel:
    entity_id: int
    canonical_name: str
    entity_type: str
    abn: str | None
    aliases: list[str]
    relationships: list[EntityRelationshipReadModel]
    observed_holdings_count_by_fund_period: list[EntityObservedHoldingsCountReadModel]


@dataclass(frozen=True)
class EntityResolutionQueueListItem:
    id: int
    holding_id: int
    raw_name: str | None
    fund_code: str
    fund_name: str
    option_name: str
    reporting_period_end_date: date
    status: str
    top_candidate_score: Decimal
    opened_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True)
class EntityResolutionQueueCandidate:
    entity_id: int
    canonical_name: str
    entity_type: str
    abn: str | None
    aliases: list[str]


@dataclass(frozen=True)
class EntityResolutionQueueHoldingSummary:
    holding_id: int
    raw_name: str | None
    source_file_id: int
    fund_code: str
    fund_name: str
    option_name: str
    reporting_period_end_date: date
    security_identifier_type: str | None
    security_identifier_value: str | None


@dataclass(frozen=True)
class EntityResolutionQueueDetailReadModel:
    queue_item: EntityResolutionQueueListItem
    holding: EntityResolutionQueueHoldingSummary
    candidates: list[EntityResolutionQueueCandidate]
    evidence_json: dict[str, object]
    candidate_entity_ids: list[int]
    resolved_by: str | None
    notes: str | None


@dataclass(frozen=True)
class SchemaReviewQueueListItem:
    id: int
    adapter_key: str
    source_file_id: int | None
    source_url: str
    checksum: str
    fund_code: str | None
    fund_name: str | None
    review_reason: str
    status: str
    approved_mapping_version_id: str | None
    observed_schema_fingerprint: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ApprovedMappingVersionSummary:
    id: str
    adapter_key: str
    schema_fingerprint: str
    approved_by: str
    approved_at: datetime
    notes: str | None


@dataclass(frozen=True)
class SchemaReviewQueueDetailReadModel:
    review_item: SchemaReviewQueueListItem
    source_file: SourceFileSummary | None
    approved_mapping_version: ApprovedMappingVersionSummary | None
    drift_summary_json: dict[str, object]
    sample_rows_json: list[list[str]]


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


def list_entity_resolution_queue_items(
    session: Session,
    *,
    status_filter: str = "open",
) -> list[EntityResolutionQueueListItem]:
    query = (
        select(
            EntityResolutionQueue.id,
            EntityResolutionQueue.holding_id,
            Holding.raw_name,
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            InvestmentOption.source_option_name.label("option_name"),
            ReportingPeriod.period_end_date.label("reporting_period_end_date"),
            EntityResolutionQueue.status,
            EntityResolutionQueue.top_candidate_score,
            EntityResolutionQueue.opened_at,
            EntityResolutionQueue.resolved_at,
        )
        .join(Holding, Holding.id == EntityResolutionQueue.holding_id)
        .join(Fund, Fund.id == Holding.source_fund_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
        .order_by(EntityResolutionQueue.opened_at.desc(), EntityResolutionQueue.id.desc())
    )
    if status_filter != "all":
        query = query.where(EntityResolutionQueue.status == status_filter)

    rows = session.execute(query).all()
    return [
        EntityResolutionQueueListItem(
            id=row.id,
            holding_id=row.holding_id,
            raw_name=row.raw_name,
            fund_code=row.fund_code,
            fund_name=row.fund_name,
            option_name=row.option_name,
            reporting_period_end_date=row.reporting_period_end_date,
            status=row.status,
            top_candidate_score=row.top_candidate_score,
            opened_at=row.opened_at,
            resolved_at=row.resolved_at,
        )
        for row in rows
    ]


def get_entity_resolution_queue_detail(
    session: Session,
    *,
    queue_item_id: int,
) -> EntityResolutionQueueDetailReadModel | None:
    row = session.execute(
        select(
            EntityResolutionQueue.id,
            EntityResolutionQueue.holding_id,
            EntityResolutionQueue.candidate_entity_ids,
            EntityResolutionQueue.top_candidate_score,
            EntityResolutionQueue.evidence_json,
            EntityResolutionQueue.status,
            EntityResolutionQueue.opened_at,
            EntityResolutionQueue.resolved_at,
            EntityResolutionQueue.resolved_by,
            EntityResolutionQueue.notes,
            Holding.raw_name,
            Holding.source_file_id,
            Holding.security_identifier_type,
            Holding.security_identifier_value,
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            InvestmentOption.source_option_name.label("option_name"),
            ReportingPeriod.period_end_date.label("reporting_period_end_date"),
        )
        .join(Holding, Holding.id == EntityResolutionQueue.holding_id)
        .join(Fund, Fund.id == Holding.source_fund_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
        .where(EntityResolutionQueue.id == queue_item_id)
    ).one_or_none()
    if row is None:
        return None

    queue_item = EntityResolutionQueueListItem(
        id=row.id,
        holding_id=row.holding_id,
        raw_name=row.raw_name,
        fund_code=row.fund_code,
        fund_name=row.fund_name,
        option_name=row.option_name,
        reporting_period_end_date=row.reporting_period_end_date,
        status=row.status,
        top_candidate_score=row.top_candidate_score,
        opened_at=row.opened_at,
        resolved_at=row.resolved_at,
    )
    holding = EntityResolutionQueueHoldingSummary(
        holding_id=row.holding_id,
        raw_name=row.raw_name,
        source_file_id=row.source_file_id,
        fund_code=row.fund_code,
        fund_name=row.fund_name,
        option_name=row.option_name,
        reporting_period_end_date=row.reporting_period_end_date,
        security_identifier_type=row.security_identifier_type,
        security_identifier_value=row.security_identifier_value,
    )

    candidate_entity_ids = [int(entity_id) for entity_id in (row.candidate_entity_ids or [])]
    candidate_rows = session.execute(
        select(
            Entity.id,
            Entity.canonical_name,
            Entity.entity_type,
            Entity.abn,
        )
        .where(Entity.id.in_(candidate_entity_ids))
        .order_by(Entity.id.asc())
    ).all() if candidate_entity_ids else []
    aliases_by_entity_id: dict[int, list[str]] = {}
    if candidate_entity_ids:
        alias_rows = session.execute(
            select(EntityAlias.entity_id, EntityAlias.alias)
            .where(EntityAlias.entity_id.in_(candidate_entity_ids))
            .order_by(EntityAlias.alias.asc(), EntityAlias.id.asc())
        ).all()
        for alias_row in alias_rows:
            aliases_by_entity_id.setdefault(int(alias_row.entity_id), []).append(alias_row.alias)

    candidate_rows_by_id = {
        int(candidate_row.id): EntityResolutionQueueCandidate(
            entity_id=int(candidate_row.id),
            canonical_name=candidate_row.canonical_name,
            entity_type=candidate_row.entity_type,
            abn=candidate_row.abn,
            aliases=aliases_by_entity_id.get(int(candidate_row.id), []),
        )
        for candidate_row in candidate_rows
    }
    candidates = [
        candidate_rows_by_id[candidate_entity_id]
        for candidate_entity_id in candidate_entity_ids
        if candidate_entity_id in candidate_rows_by_id
    ]

    return EntityResolutionQueueDetailReadModel(
        queue_item=queue_item,
        holding=holding,
        candidates=candidates,
        evidence_json=dict(row.evidence_json or {}),
        candidate_entity_ids=candidate_entity_ids,
        resolved_by=row.resolved_by,
        notes=row.notes,
    )


def list_schema_review_queue_items(
    session: Session,
    *,
    status_filter: str = "open",
) -> list[SchemaReviewQueueListItem]:
    query = (
        select(
            SchemaReviewQueue.id,
            SchemaReviewQueue.adapter_key,
            SchemaReviewQueue.source_file_id,
            SchemaReviewQueue.source_url,
            SchemaReviewQueue.checksum,
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            SchemaReviewQueue.review_reason,
            SchemaReviewQueue.status,
            SchemaReviewQueue.approved_mapping_version_id,
            SchemaReviewQueue.observed_schema_fingerprint,
            SchemaReviewQueue.created_at,
            SchemaReviewQueue.updated_at,
        )
        .outerjoin(SourceFile, SourceFile.id == SchemaReviewQueue.source_file_id)
        .outerjoin(Fund, Fund.id == SourceFile.fund_id)
        .order_by(SchemaReviewQueue.created_at.desc(), SchemaReviewQueue.id.desc())
    )
    if status_filter != "all":
        query = query.where(SchemaReviewQueue.status == status_filter)

    rows = session.execute(query).all()
    return [
        SchemaReviewQueueListItem(
            id=row.id,
            adapter_key=row.adapter_key,
            source_file_id=row.source_file_id,
            source_url=row.source_url,
            checksum=row.checksum,
            fund_code=row.fund_code,
            fund_name=row.fund_name,
            review_reason=row.review_reason,
            status=row.status,
            approved_mapping_version_id=row.approved_mapping_version_id,
            observed_schema_fingerprint=row.observed_schema_fingerprint,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def get_schema_review_queue_detail(
    session: Session,
    *,
    review_item_id: int,
) -> SchemaReviewQueueDetailReadModel | None:
    review_item_row = session.execute(
        select(
            SchemaReviewQueue.id,
            SchemaReviewQueue.adapter_key,
            SchemaReviewQueue.source_file_id,
            SchemaReviewQueue.source_url,
            SchemaReviewQueue.checksum,
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            SchemaReviewQueue.review_reason,
            SchemaReviewQueue.status,
            SchemaReviewQueue.approved_mapping_version_id,
            SchemaReviewQueue.observed_schema_fingerprint,
            SchemaReviewQueue.created_at,
            SchemaReviewQueue.updated_at,
            SchemaReviewQueue.drift_summary_json,
            SchemaReviewQueue.sample_rows_json,
        )
        .outerjoin(SourceFile, SourceFile.id == SchemaReviewQueue.source_file_id)
        .outerjoin(Fund, Fund.id == SourceFile.fund_id)
        .where(SchemaReviewQueue.id == review_item_id)
    ).one_or_none()
    if review_item_row is None:
        return None

    review_item = SchemaReviewQueueListItem(
        id=review_item_row.id,
        adapter_key=review_item_row.adapter_key,
        source_file_id=review_item_row.source_file_id,
        source_url=review_item_row.source_url,
        checksum=review_item_row.checksum,
        fund_code=review_item_row.fund_code,
        fund_name=review_item_row.fund_name,
        review_reason=review_item_row.review_reason,
        status=review_item_row.status,
        approved_mapping_version_id=review_item_row.approved_mapping_version_id,
        observed_schema_fingerprint=review_item_row.observed_schema_fingerprint,
        created_at=review_item_row.created_at,
        updated_at=review_item_row.updated_at,
    )

    source_file = None
    if review_item.source_file_id is not None:
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
            .where(SourceFile.id == review_item.source_file_id)
        ).one_or_none()
        if source_file_row is not None:
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

    approved_mapping_version = None
    if review_item.approved_mapping_version_id is not None:
        mapping_version = session.get(AdapterMappingVersion, review_item.approved_mapping_version_id)
        if mapping_version is not None:
            approved_mapping_version = ApprovedMappingVersionSummary(
                id=mapping_version.id,
                adapter_key=mapping_version.adapter_key,
                schema_fingerprint=mapping_version.schema_fingerprint,
                approved_by=mapping_version.approved_by,
                approved_at=mapping_version.approved_at,
                notes=mapping_version.notes,
            )

    return SchemaReviewQueueDetailReadModel(
        review_item=review_item,
        source_file=source_file,
        approved_mapping_version=approved_mapping_version,
        drift_summary_json=dict(review_item_row.drift_summary_json or {}),
        sample_rows_json=[list(row) for row in review_item_row.sample_rows_json or []],
    )


def update_schema_review_queue_status(
    session: Session,
    *,
    review_item_id: int,
    new_status: str,
) -> SchemaReviewQueueDetailReadModel | None:
    review_item = session.get(SchemaReviewQueue, review_item_id)
    if review_item is None:
        return None
    if new_status not in {"resolved", "rejected"}:
        raise ValueError("new_status must be 'resolved' or 'rejected'")
    if review_item.status != "open":
        raise ValueError(f"review item {review_item_id} is already {review_item.status}")

    review_item.status = new_status
    session.flush()
    return get_schema_review_queue_detail(session, review_item_id=review_item_id)


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


def get_cross_adapter_holdings_by_name(
    session: Session,
    *,
    name: str,
) -> CrossAdapterHoldingsReadModel | None:
    lookup_name = name.strip()
    if lookup_name == "":
        raise ValueError("name must not be blank")

    normalized_lookup_name = normalise_name(lookup_name)
    rows = _load_current_cross_adapter_rows(session)

    observations: list[CrossAdapterObservationReadModel] = []
    for row in rows:
        normalized_name = normalise_name(row.raw_name)
        if normalized_lookup_name != normalized_name:
            continue
        observations.append(
            CrossAdapterObservationReadModel(
                normalized_name=normalized_name,
                raw_name=row.raw_name,
                source_file_id=row.source_file_id,
                fund_code=row.fund_code,
                fund_name=row.fund_name,
                option_code=row.option_code,
                option_name=row.option_name,
                reporting_period_end_date=row.reporting_period_end_date,
                disclosure_completeness=row.disclosure_completeness,
                value_aud=row.value_aud,
                ownership_pct=row.ownership_pct,
                value_band_raw=row.value_band_raw,
                is_aggregate=row.is_aggregate,
            )
        )

    return _build_cross_adapter_holdings_read_model(
        entity_id=None,
        lookup_name=lookup_name,
        normalized_lookup_name=normalized_lookup_name,
        observations=observations,
    )


def get_cross_adapter_holdings_by_entity_id(
    session: Session,
    *,
    entity_id: int,
) -> CrossAdapterHoldingsReadModel | None:
    entity = session.get(Entity, entity_id)
    if entity is None:
        return None

    normalized_names = {
        normalise_name(entity.canonical_name),
        *[
            normalise_name(alias)
            for alias in session.scalars(
                select(EntityAlias.alias).where(EntityAlias.entity_id == entity_id).order_by(EntityAlias.alias.asc())
            ).all()
        ],
    }

    rows = _load_current_cross_adapter_rows(session)
    observations: list[CrossAdapterObservationReadModel] = []
    for row in rows:
        normalized_name = normalise_name(row.raw_name)
        if row.entity_id != entity_id and normalized_name not in normalized_names:
            continue
        observations.append(
            CrossAdapterObservationReadModel(
                normalized_name=normalized_name,
                raw_name=row.raw_name,
                source_file_id=row.source_file_id,
                fund_code=row.fund_code,
                fund_name=row.fund_name,
                option_code=row.option_code,
                option_name=row.option_name,
                reporting_period_end_date=row.reporting_period_end_date,
                disclosure_completeness=row.disclosure_completeness,
                value_aud=row.value_aud,
                ownership_pct=row.ownership_pct,
                value_band_raw=row.value_band_raw,
                is_aggregate=row.is_aggregate,
            )
        )

    return _build_cross_adapter_holdings_read_model(
        entity_id=entity_id,
        lookup_name=entity.canonical_name,
        normalized_lookup_name=normalise_name(entity.canonical_name),
        observations=observations,
    )


def get_canonical_entity_detail(
    session: Session,
    *,
    entity_id: int,
) -> CanonicalEntityDetailReadModel | None:
    entity = session.get(Entity, entity_id)
    if entity is None:
        return None

    alias_rows = session.scalars(
        select(EntityAlias.alias).where(EntityAlias.entity_id == entity_id).order_by(EntityAlias.is_preferred.desc(), EntityAlias.alias.asc())
    ).all()
    aliases = list(dict.fromkeys([entity.canonical_name, *alias_rows]))
    normalized_aliases = {normalise_name(alias) for alias in aliases}

    relationship_rows = session.execute(
        select(
            EntityRelationship.id,
            EntityRelationship.from_entity_id,
            EntityRelationship.to_entity_id,
            EntityRelationship.relationship_type,
            EntityRelationship.source,
            EntityRelationship.notes,
        )
        .where(
            (EntityRelationship.from_entity_id == entity_id) | (EntityRelationship.to_entity_id == entity_id)
        )
        .order_by(EntityRelationship.id.asc())
    ).all()
    relationships = [
        EntityRelationshipReadModel(
            relationship_id=row.id,
            from_entity_id=row.from_entity_id,
            to_entity_id=row.to_entity_id,
            relationship_type=row.relationship_type,
            source=row.source,
            notes=row.notes,
        )
        for row in relationship_rows
    ]

    holding_rows = _load_current_cross_adapter_rows(session)
    matched_rows = [
        row
        for row in holding_rows
        if row.entity_id == entity_id or normalise_name(row.raw_name) in normalized_aliases
    ]
    counts_by_fund_period: dict[tuple[str, str, date], int] = {}
    for row in matched_rows:
        key = (row.fund_code, row.fund_name, row.reporting_period_end_date)
        counts_by_fund_period[key] = counts_by_fund_period.get(key, 0) + 1

    observed_counts = [
        EntityObservedHoldingsCountReadModel(
            fund_code=fund_code,
            fund_name=fund_name,
            reporting_period_end_date=reporting_period_end_date,
            observation_count=observation_count,
        )
        for (fund_code, fund_name, reporting_period_end_date), observation_count in sorted(
            counts_by_fund_period.items(),
            key=lambda item: (item[0][0], item[0][2]),
        )
    ]

    return CanonicalEntityDetailReadModel(
        entity_id=entity.id,
        canonical_name=entity.canonical_name,
        entity_type=entity.entity_type,
        abn=entity.abn,
        aliases=aliases,
        relationships=relationships,
        observed_holdings_count_by_fund_period=observed_counts,
    )


def _load_current_cross_adapter_rows(session: Session):
    return session.execute(
        select(
            Holding.raw_name,
            Holding.entity_id,
            Holding.source_file_id,
            Holding.is_aggregate,
            Holding.disclosure_completeness,
            Holding.value_aud,
            Holding.ownership_pct,
            Holding.value_band_raw,
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            InvestmentOption.source_option_code.label("option_code"),
            InvestmentOption.source_option_name.label("option_name"),
            ReportingPeriod.period_end_date.label("reporting_period_end_date"),
        )
        .join(Fund, Fund.id == Holding.source_fund_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
        .join(SourceFile, SourceFile.id == Holding.source_file_id)
        .where(
            Holding.raw_name.is_not(None),
            Holding.is_aggregate.is_(False),
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
        )
        .order_by(
            Fund.code.asc(),
            InvestmentOption.source_option_name.asc(),
            ReportingPeriod.period_end_date.desc(),
            Holding.source_file_id.asc(),
            Holding.source_row_number.asc(),
        )
    ).all()

def _build_cross_adapter_holdings_read_model(
    *,
    entity_id: int | None,
    lookup_name: str,
    normalized_lookup_name: str,
    observations: list[CrossAdapterObservationReadModel],
) -> CrossAdapterHoldingsReadModel | None:
    if not observations:
        return None

    observations.sort(
        key=lambda item: (
            item.normalized_name,
            item.fund_code,
            item.option_name,
            item.reporting_period_end_date,
            item.source_file_id,
        )
    )
    return CrossAdapterHoldingsReadModel(
        entity_id=entity_id,
        lookup_name=lookup_name,
        normalized_lookup_name=normalized_lookup_name,
        matched_normalized_names=sorted({item.normalized_name for item in observations}),
        matched_raw_names=sorted({item.raw_name for item in observations}),
        observation_count=len(observations),
        fund_count=len({item.fund_code for item in observations}),
        observations=observations,
    )
