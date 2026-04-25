from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
    HoldingRelationship,
    InvestmentOption,
    ReportingPeriod,
    SchemaReviewQueue,
    SourceFile,
    TaxonomyMapping,
)
from app.entity_resolution.australiansuper_stable_matched_assets import (
    AUSTRALIANSUPER_STABLE_MATCHED_ASSET_PROOF_KEY,
    AUSTRALIANSUPER_STABLE_MATCHED_ASSET_RELATIONSHIP_ROLE,
    AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE,
    AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGET_ROW_NUMBERS,
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
class ManagerObservationReadModel:
    holding_id: int
    raw_name: str
    source_file_id: int
    source_row_number: int
    source_fund_id: int
    fund_code: str
    fund_name: str
    source_option_id: int
    option_code: str
    option_name: str
    reporting_period_end_date: date
    canonical_asset_class_code: str
    source_asset_class_raw: str
    source_subclass_raw: str | None
    disclosure_completeness: str
    value_aud: Decimal | None
    ownership_pct: Decimal | None
    value_band_raw: str | None
    currency_raw: str | None
    observation_kind: str
    disclosure_label: str
    observation_kind_label: str
    confidence_label: str
    confidence_detail: str
    is_non_precise: bool


@dataclass(frozen=True)
class ManagerRoleOptionGroupReadModel:
    source_option_id: int
    option_code: str
    option_name: str
    row_count: int
    value_aud_total: Decimal
    rows: list[ManagerObservationReadModel]


@dataclass(frozen=True)
class ManagerRoleFundGroupReadModel:
    source_fund_id: int
    fund_code: str
    fund_name: str
    row_count: int
    value_aud_total: Decimal
    option_groups: list[ManagerRoleOptionGroupReadModel]


@dataclass(frozen=True)
class ManagerDetailReadModel:
    entity_id: int
    canonical_name: str
    entity_type: str
    abn: str | None
    abn_review_source: str | None
    abn_reviewed_by: str | None
    abn_reviewed_at: date | None
    registered_name_on_abr: str | None
    acn: str | None
    asic_company_status: str | None
    asic_company_type: str | None
    asic_registration_date: date | None
    asic_next_review_date: date | None
    asic_record_url: str | None
    asic_review_source: str | None
    asic_reviewed_by: str | None
    asic_reviewed_at: date | None
    aliases: list[str]
    matched_raw_names: list[str]
    asset_classes: list[str]
    role_classes: list[str]
    relationships: list[EntityRelationshipReadModel]
    observation_count: int
    fund_count: int
    latest_reporting_period: date | None
    entity_confidence_label: str
    entity_confidence_detail: str
    disclosure_summary: list[tuple[str, int]]
    resolution_scope_note: str
    observations: list[ManagerObservationReadModel]
    manager_role_fund_count: int
    manager_role_option_count: int
    manager_role_value_aud_total: Decimal
    active_role_group_count: int
    manager_role_groups: list[ManagerRoleFundGroupReadModel]
    manager_role_rows: list[ManagerObservationReadModel]
    direct_holding_rows: list[ManagerObservationReadModel]
    issuer_role_rows: list[ManagerObservationReadModel]
    primary_observations: list[ManagerObservationReadModel]
    supplemental_observations: list[ManagerObservationReadModel]


@dataclass(frozen=True)
class CompanyObservationReadModel:
    holding_id: int
    raw_name: str
    source_file_id: int
    source_row_number: int
    fund_code: str
    fund_name: str
    option_code: str
    option_name: str
    reporting_period_end_date: date
    canonical_asset_class_code: str
    source_asset_class_raw: str
    source_subclass_raw: str | None
    disclosure_completeness: str
    value_aud: Decimal | None
    ownership_pct: Decimal | None
    value_band_raw: str | None
    currency_raw: str | None
    disclosure_label: str
    confidence_label: str
    confidence_detail: str
    is_value_band: bool


@dataclass(frozen=True)
class CompanyPeriodHistoryReadModel:
    reporting_period_end_date: date
    observation_count: int
    fund_count: int


@dataclass(frozen=True)
class CompanyDetailReadModel:
    entity_id: int
    canonical_name: str
    entity_type: str
    abn: str | None
    abn_review_source: str | None
    abn_reviewed_by: str | None
    abn_reviewed_at: date | None
    registered_name_on_abr: str | None
    acn: str | None
    asic_company_status: str | None
    asic_company_type: str | None
    asic_registration_date: date | None
    asic_next_review_date: date | None
    asic_record_url: str | None
    asic_review_source: str | None
    asic_reviewed_by: str | None
    asic_reviewed_at: date | None
    aliases: list[str]
    matched_raw_names: list[str]
    asset_classes: list[str]
    relationships: list[EntityRelationshipReadModel]
    observation_count: int
    fund_count: int
    holder_slice_count: int
    latest_reporting_period: date | None
    history_is_limited: bool
    history_note: str | None
    resolution_scope_note: str
    entity_confidence_label: str
    entity_confidence_detail: str
    disclosure_summary: list[tuple[str, int]]
    period_history: list[CompanyPeriodHistoryReadModel]
    observations: list[CompanyObservationReadModel]
    manager_role_rows: list[CompanyObservationReadModel]
    direct_holding_rows: list[CompanyObservationReadModel]
    issuer_role_rows: list[CompanyObservationReadModel]
    primary_observations: list[CompanyObservationReadModel]
    value_band_observations: list[CompanyObservationReadModel]


@dataclass(frozen=True)
class FundAssetClassMixBucketReadModel:
    disclosure_completeness: str
    observation_count: int
    precise_value_row_count: int
    precise_value_aud_total: Decimal


@dataclass(frozen=True)
class FundAssetClassMixReadModel:
    canonical_asset_class_code: str
    by_disclosure_completeness: list[FundAssetClassMixBucketReadModel]


@dataclass(frozen=True)
class FundObservationSummaryReadModel:
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
    value_aud: Decimal | None
    ownership_pct: Decimal | None
    value_band_raw: str | None
    disclosure_label: str
    observation_kind_label: str
    confidence_label: str
    confidence_detail: str


@dataclass(frozen=True)
class FundInvestmentOptionReadModel:
    option_id: int
    option_code: str
    option_name: str
    reporting_period_end_date: date | None
    observation_count: int
    asset_class_mix: list[FundAssetClassMixReadModel]
    top_direct_private_holdings: list[FundObservationSummaryReadModel]
    manager_level_aggregate_exposures: list[FundObservationSummaryReadModel]
    named_private_exposures: list[FundObservationSummaryReadModel]
    value_band_exposures: list[FundObservationSummaryReadModel]
    other_named_private_exposures: list[FundObservationSummaryReadModel]


@dataclass(frozen=True)
class FundChangeReadModel:
    available: bool
    current_reporting_period_end_date: date | None
    prior_reporting_period_end_date: date | None
    note: str | None


@dataclass(frozen=True)
class FundDetailReadModel:
    fund_id: int
    fund_code: str
    fund_name: str
    latest_reporting_period: date | None
    investment_options: list[FundInvestmentOptionReadModel]
    change_since_prior_reporting_period: FundChangeReadModel


@dataclass(frozen=True)
class MatchedAssetProofRowReadModel:
    asset_entity_id: int
    asset_entity_name: str
    entity_type: str
    source_fund_code: str
    source_fund_name: str
    option_code: str
    option_name: str
    reporting_period_end_date: date
    canonical_asset_class_code: str
    source_asset_class_raw: str
    source_subclass_raw: str | None
    disclosure_completeness: str
    ownership_pct: Decimal | None
    value_band_raw: str | None
    classification_raw: str | None
    address: str | None
    location_raw: str | None
    geo_lat: Decimal | None
    geo_lng: Decimal | None
    confidence_score: Decimal | None
    relationship_source: str
    source_file_id: int
    source_row_number: int
    metadata_attached_from_row_numbers: list[int]


@dataclass(frozen=True)
class MatchedAssetProofReadModel:
    proof_key: str
    title: str
    scope_note: str
    matched_asset_count: int
    rows: list[MatchedAssetProofRowReadModel]


@dataclass(frozen=True)
class SearchResultReadModel:
    result_kind: str
    result_kind_label: str
    title: str
    matched_on: str
    matched_on_label: str
    matched_value: str
    entity_id: int | None
    fund_code: str | None


@dataclass(frozen=True)
class SearchResultsReadModel:
    query: str
    normalized_query: str
    active_kind: str
    result_count: int
    total_result_count: int
    kind_counts: dict[str, int]
    results: list[SearchResultReadModel]


@dataclass(frozen=True)
class HomepageChangeMetricReadModel:
    label: str
    value: int | str
    trend_note: str


@dataclass(frozen=True)
class HomepageStatReadModel:
    label: str
    value: int | str
    note: str | None = None


@dataclass(frozen=True)
class HomepageFeatureEntryReadModel:
    kicker: str
    title: str
    deck: str
    result_kind: str
    entity_id: int | None
    fund_code: str | None
    search_query: str | None
    cta_label: str | None
    status_label: str | None


@dataclass(frozen=True)
class HomepageReadModel:
    latest_reporting_period: date | None
    prior_reporting_period: date | None
    change_available: bool
    change_note: str
    stats: list[HomepageStatReadModel]
    change_metrics: list[HomepageChangeMetricReadModel]
    featured_entries: list[HomepageFeatureEntryReadModel]
    editorial_note: str


@dataclass(frozen=True)
class DemoCuratedLinkReadModel:
    title: str
    deck: str
    result_kind: str
    entity_id: int | None
    search_query: str | None
    cta_label: str
    status_label: str


@dataclass(frozen=True)
class DemoDashboardReadModel:
    homepage: HomepageReadModel
    curated_links: list[DemoCuratedLinkReadModel]


@dataclass(frozen=True)
class DemoEntityExplorerFilterOption:
    value: str
    label: str


@dataclass(frozen=True)
class DemoEntityExplorerRowReadModel:
    entity_id: int
    entity_name: str
    entity_type: str
    fund_count: int
    option_count: int
    row_count: int
    total_value_aud: Decimal
    ownership_count: int
    disclosure_mix: list[tuple[str, int]]


@dataclass(frozen=True)
class DemoEntityExplorerReadModel:
    rows: list[DemoEntityExplorerRowReadModel]
    total_rows: int
    page: int
    page_size: int
    total_pages: int
    sort: str
    active_entity_type: str
    selected_disclosure_completeness: list[str]
    selected_funds: list[str]
    selected_asset_classes: list[str]
    sort_options: list[DemoEntityExplorerFilterOption]
    entity_type_options: list[DemoEntityExplorerFilterOption]
    disclosure_options: list[DemoEntityExplorerFilterOption]
    fund_options: list[DemoEntityExplorerFilterOption]
    asset_class_options: list[DemoEntityExplorerFilterOption]


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


def approve_schema_review_mapping(
    session: Session,
    *,
    review_item_id: int,
    mapping_version_id: str,
    approved_by: str,
    notes: str | None,
    structural_expectations_json: dict[str, object],
    taxonomy_mappings_payload: list[dict[str, object]],
) -> SchemaReviewQueueDetailReadModel | None:
    review_item = session.get(SchemaReviewQueue, review_item_id)
    if review_item is None:
        return None
    if review_item.status != "open":
        raise ValueError(f"review item {review_item_id} is already {review_item.status}")

    normalized_mapping_version_id = mapping_version_id.strip()
    if normalized_mapping_version_id == "":
        raise ValueError("mapping_version_id is required")
    if session.get(AdapterMappingVersion, normalized_mapping_version_id) is not None:
        raise ValueError(f"mapping version {normalized_mapping_version_id} already exists")

    normalized_approved_by = approved_by.strip()
    if normalized_approved_by == "":
        raise ValueError("approved_by is required")
    if not isinstance(structural_expectations_json, dict):
        raise ValueError("structural_expectations_json must be an object")
    if not taxonomy_mappings_payload:
        raise ValueError("taxonomy_mappings must contain at least one row")

    source_file = session.get(SourceFile, review_item.source_file_id) if review_item.source_file_id is not None else None
    schema_fingerprint = review_item.observed_schema_fingerprint or (source_file.schema_fingerprint if source_file else None)
    if schema_fingerprint is None or schema_fingerprint.strip() == "":
        raise ValueError("schema review item does not have an observed schema_fingerprint")

    approved_at = datetime.now(UTC)
    effective_from_period_id = source_file.reporting_period_id if source_file is not None else None

    mapping_version = AdapterMappingVersion(
        id=normalized_mapping_version_id,
        adapter_key=review_item.adapter_key,
        schema_fingerprint=schema_fingerprint,
        structural_expectations_json=structural_expectations_json,
        notes=_normalize_optional_text(notes),
        approved_by=normalized_approved_by,
        approved_at=approved_at,
        effective_from_period_id=effective_from_period_id,
        effective_to_period_id=None,
        is_active=True,
    )
    session.add(mapping_version)
    session.flush()

    seen_taxonomy_keys: set[tuple[object, ...]] = set()
    for row_payload in taxonomy_mappings_payload:
        taxonomy_row = _build_taxonomy_mapping_from_payload(
            adapter_key=review_item.adapter_key,
            mapping_version_id=normalized_mapping_version_id,
            approved_by=normalized_approved_by,
            approved_at=approved_at,
            effective_from_period_id=effective_from_period_id,
            payload=row_payload,
        )
        taxonomy_key = (
            taxonomy_row.source_asset_class_raw,
            taxonomy_row.source_filter_raw,
            taxonomy_row.source_sub_filter_raw,
            taxonomy_row.source_section_raw,
            taxonomy_row.is_aggregate_default,
        )
        if taxonomy_key in seen_taxonomy_keys:
            raise ValueError(
                "taxonomy_mappings contains duplicate scope rows for "
                f"{taxonomy_key!r}"
            )
        seen_taxonomy_keys.add(taxonomy_key)
        session.add(taxonomy_row)

    review_item.approved_mapping_version_id = normalized_mapping_version_id
    review_item.status = "resolved"
    if source_file is not None:
        source_file.mapping_version_id = normalized_mapping_version_id
    session.flush()
    return get_schema_review_queue_detail(session, review_item_id=review_item_id)


def _build_taxonomy_mapping_from_payload(
    *,
    adapter_key: str,
    mapping_version_id: str,
    approved_by: str,
    approved_at: datetime,
    effective_from_period_id: int | None,
    payload: dict[str, object],
) -> TaxonomyMapping:
    if not isinstance(payload, dict):
        raise ValueError("taxonomy_mappings rows must be objects")

    source_asset_class_raw = _require_nonempty_text(payload.get("source_asset_class_raw"), "source_asset_class_raw")
    canonical_asset_class_code = _require_nonempty_text(
        payload.get("canonical_asset_class_code"),
        "canonical_asset_class_code",
    )
    is_aggregate_default = payload.get("is_aggregate_default")
    if not isinstance(is_aggregate_default, bool):
        raise ValueError("taxonomy_mappings.is_aggregate_default must be true or false")

    disclosure_completeness_default = payload.get("disclosure_completeness_default")
    if disclosure_completeness_default is not None and not isinstance(disclosure_completeness_default, str):
        raise ValueError("taxonomy_mappings.disclosure_completeness_default must be a string or null")

    return TaxonomyMapping(
        adapter_key=adapter_key,
        mapping_version=mapping_version_id,
        source_asset_class_raw=source_asset_class_raw,
        source_filter_raw=_normalize_optional_text(payload.get("source_filter_raw")),
        source_sub_filter_raw=_normalize_optional_text(payload.get("source_sub_filter_raw")),
        source_section_raw=_normalize_optional_text(payload.get("source_section_raw")),
        canonical_asset_class_code=canonical_asset_class_code,
        is_aggregate_default=is_aggregate_default,
        disclosure_completeness_default=_normalize_optional_text(disclosure_completeness_default),
        notes=_normalize_optional_text(payload.get("notes")),
        approved_by=approved_by,
        approved_at=approved_at,
        effective_from_period_id=effective_from_period_id,
        effective_to_period_id=None,
    )


def _require_nonempty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"taxonomy_mappings.{field_name} is required")
    return value.strip()


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional text fields must be strings or null")
    normalized = value.strip()
    if normalized == "":
        return None
    return normalized


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

    aliases = _get_entity_aliases(session, entity=entity)
    normalized_aliases = {normalise_name(alias) for alias in aliases}
    relationships = _get_entity_relationships(session, entity_id=entity_id)

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


def get_manager_detail(
    session: Session,
    *,
    entity_id: int,
) -> ManagerDetailReadModel | None:
    entity = session.get(Entity, entity_id)
    if entity is None or entity.entity_type != "manager":
        return None

    aliases = _get_entity_aliases(session, entity=entity)
    normalized_aliases = {normalise_name(alias) for alias in aliases}
    relationships = _get_entity_relationships(session, entity_id=entity_id)
    entity_confidence_label, entity_confidence_detail = _company_entity_confidence(
        confidence_tier=entity.confidence_tier,
    )

    rows = session.execute(
        select(
            Holding.id.label("holding_id"),
            Holding.raw_name,
            Holding.entity_id,
            Holding.manager_entity_id,
            Holding.issuer_entity_id,
            Holding.source_file_id,
            Holding.source_row_number,
            Holding.disclosure_completeness,
            Holding.value_aud,
            Holding.ownership_pct,
            Holding.value_band_raw,
            Holding.currency_raw,
            Holding.source_asset_class_raw,
            Holding.source_subclass_raw,
            Holding.classification_raw,
            CanonicalAssetClass.code.label("canonical_asset_class_code"),
            Fund.id.label("source_fund_id"),
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            InvestmentOption.id.label("source_option_id"),
            InvestmentOption.source_option_code.label("option_code"),
            InvestmentOption.source_option_name.label("option_name"),
            ReportingPeriod.period_end_date.label("reporting_period_end_date"),
        )
        .join(Fund, Fund.id == Holding.source_fund_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
        .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
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

    issuer_holding_ids = _get_issuer_holding_ids(session, entity_id=entity_id)
    manager_role_rows: list[ManagerObservationReadModel] = []
    direct_holding_rows: list[ManagerObservationReadModel] = []
    issuer_role_rows: list[ManagerObservationReadModel] = []
    for row in rows:
        if row.raw_name is None:
            continue
        normalized_name = normalise_name(row.raw_name)
        observation_kind = _derive_manager_observation_kind(
            entity_id=entity_id,
            manager_entity_id=row.manager_entity_id,
            issuer_entity_id=row.issuer_entity_id,
            disclosure_completeness=row.disclosure_completeness,
            ownership_pct=row.ownership_pct,
            source_subclass_raw=row.source_subclass_raw,
            classification_raw=row.classification_raw,
        )
        is_manager_role = row.manager_entity_id == entity_id or (
            row.entity_id == entity_id and observation_kind == "manager_rollup"
        )
        is_direct_holding = row.entity_id == entity_id
        is_issuer_role = row.issuer_entity_id == entity_id or int(row.holding_id) in issuer_holding_ids
        is_legacy_alias_match = (
            not (is_manager_role or is_direct_holding or is_issuer_role)
            and normalized_name in normalized_aliases
        )
        if not (is_manager_role or is_direct_holding or is_issuer_role or is_legacy_alias_match):
            continue
        row_confidence_label, row_confidence_detail = _company_observation_confidence(
            current_entity_id=entity_id,
            observation_entity_id=row.entity_id,
            observation_raw_name=row.raw_name,
            canonical_name=entity.canonical_name,
            normalized_aliases=normalized_aliases,
            entity_confidence_label=entity_confidence_label,
            entity_confidence_detail=entity_confidence_detail,
        )
        observation = ManagerObservationReadModel(
            holding_id=int(row.holding_id),
            raw_name=row.raw_name,
            source_file_id=row.source_file_id,
            source_row_number=row.source_row_number,
            source_fund_id=row.source_fund_id,
            fund_code=row.fund_code,
            fund_name=row.fund_name,
            source_option_id=row.source_option_id,
            option_code=row.option_code,
            option_name=row.option_name,
            reporting_period_end_date=row.reporting_period_end_date,
            canonical_asset_class_code=row.canonical_asset_class_code,
            source_asset_class_raw=row.source_asset_class_raw,
            source_subclass_raw=row.source_subclass_raw,
            disclosure_completeness=row.disclosure_completeness,
            value_aud=row.value_aud,
            ownership_pct=row.ownership_pct,
            value_band_raw=row.value_band_raw,
            currency_raw=row.currency_raw,
            observation_kind=observation_kind,
            disclosure_label=_humanize_disclosure_completeness(row.disclosure_completeness),
            observation_kind_label=_humanize_observation_kind(observation_kind),
            confidence_label=row_confidence_label,
            confidence_detail=row_confidence_detail,
            is_non_precise=row.value_aud is None and row.ownership_pct is None,
        )
        if is_manager_role:
            manager_role_rows.append(observation)
        if is_direct_holding or is_legacy_alias_match:
            direct_holding_rows.append(observation)
        if is_issuer_role:
            issuer_role_rows.append(observation)

    observations = _unique_observations_by_holding_id(
        [*manager_role_rows, *direct_holding_rows, *issuer_role_rows],
    )

    latest_reporting_period = max(
        (observation.reporting_period_end_date for observation in observations),
        default=None,
    )
    role_classes = _derive_manager_role_classes(
        manager_role_rows=manager_role_rows,
        direct_holding_rows=direct_holding_rows,
        issuer_role_rows=issuer_role_rows,
    )
    disclosure_counter = Counter(observation.disclosure_completeness for observation in observations)
    disclosure_summary = [
        (_humanize_disclosure_completeness(disclosure_key), disclosure_counter[disclosure_key])
        for disclosure_key in sorted(
            disclosure_counter,
            key=lambda item: DISCLOSURE_COMPLETENESS_SORT_ORDER.get(item, 999),
        )
    ]
    primary_observations = [observation for observation in observations if not observation.is_non_precise]
    supplemental_observations = [observation for observation in observations if observation.is_non_precise]
    manager_role_value_aud_total = sum(
        (observation.value_aud for observation in manager_role_rows if observation.value_aud is not None),
        Decimal("0"),
    )
    return ManagerDetailReadModel(
        entity_id=entity.id,
        canonical_name=entity.canonical_name,
        entity_type=entity.entity_type,
        abn=entity.abn,
        abn_review_source=entity.abn_review_source,
        abn_reviewed_by=entity.abn_reviewed_by,
        abn_reviewed_at=entity.abn_reviewed_at,
        registered_name_on_abr=entity.registered_name_on_abr,
        acn=entity.acn,
        asic_company_status=entity.asic_company_status,
        asic_company_type=entity.asic_company_type,
        asic_registration_date=entity.asic_registration_date,
        asic_next_review_date=entity.asic_next_review_date,
        asic_record_url=entity.asic_record_url,
        asic_review_source=entity.asic_review_source,
        asic_reviewed_by=entity.asic_reviewed_by,
        asic_reviewed_at=entity.asic_reviewed_at,
        aliases=aliases,
        matched_raw_names=sorted({observation.raw_name for observation in observations}),
        asset_classes=sorted({observation.canonical_asset_class_code for observation in observations}),
        role_classes=role_classes,
        relationships=relationships,
        observation_count=len(observations),
        fund_count=len({observation.fund_code for observation in observations}),
        latest_reporting_period=latest_reporting_period,
        entity_confidence_label=entity_confidence_label,
        entity_confidence_detail=entity_confidence_detail,
        disclosure_summary=disclosure_summary,
        resolution_scope_note=(
            "Current manager detail stays on stored disclosed rows only. No look-through traversal, no "
            "cross-fund total, and no extra relationship inference is added on this page."
        ),
        observations=observations,
        manager_role_fund_count=len({observation.source_fund_id for observation in manager_role_rows}),
        manager_role_option_count=len({observation.source_option_id for observation in manager_role_rows}),
        manager_role_value_aud_total=manager_role_value_aud_total,
        active_role_group_count=sum(
            1
            for role_rows in (manager_role_rows, direct_holding_rows, issuer_role_rows)
            if role_rows
        ),
        manager_role_groups=_build_manager_role_groups(manager_role_rows),
        manager_role_rows=manager_role_rows,
        direct_holding_rows=direct_holding_rows,
        issuer_role_rows=issuer_role_rows,
        primary_observations=primary_observations,
        supplemental_observations=supplemental_observations,
    )


def get_company_detail(
    session: Session,
    *,
    entity_id: int,
) -> CompanyDetailReadModel | None:
    entity = session.get(Entity, entity_id)
    if entity is None or entity.entity_type != "company":
        return None

    aliases = _get_entity_aliases(session, entity=entity)
    normalized_aliases = {normalise_name(alias) for alias in aliases}
    relationships = _get_entity_relationships(session, entity_id=entity_id)
    entity_confidence_label, entity_confidence_detail = _company_entity_confidence(
        confidence_tier=entity.confidence_tier,
    )

    rows = session.execute(
        select(
            Holding.id.label("holding_id"),
            Holding.raw_name,
            Holding.entity_id,
            Holding.manager_entity_id,
            Holding.issuer_entity_id,
            Holding.source_file_id,
            Holding.source_row_number,
            Holding.disclosure_completeness,
            Holding.value_aud,
            Holding.ownership_pct,
            Holding.value_band_raw,
            Holding.currency_raw,
            Holding.source_asset_class_raw,
            Holding.source_subclass_raw,
            CanonicalAssetClass.code.label("canonical_asset_class_code"),
            Fund.code.label("fund_code"),
            Fund.name.label("fund_name"),
            InvestmentOption.source_option_code.label("option_code"),
            InvestmentOption.source_option_name.label("option_name"),
            ReportingPeriod.period_end_date.label("reporting_period_end_date"),
        )
        .join(Fund, Fund.id == Holding.source_fund_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
        .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
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

    issuer_holding_ids = _get_issuer_holding_ids(session, entity_id=entity_id)
    manager_role_rows: list[CompanyObservationReadModel] = []
    direct_holding_rows: list[CompanyObservationReadModel] = []
    issuer_role_rows: list[CompanyObservationReadModel] = []
    for row in rows:
        if row.raw_name is None:
            continue
        normalized_name = normalise_name(row.raw_name)
        is_manager_role = row.manager_entity_id == entity_id
        is_direct_holding = row.entity_id == entity_id
        is_issuer_role = row.issuer_entity_id == entity_id or int(row.holding_id) in issuer_holding_ids
        is_legacy_alias_match = (
            not (is_manager_role or is_direct_holding or is_issuer_role)
            and normalized_name in normalized_aliases
        )
        if not (is_manager_role or is_direct_holding or is_issuer_role or is_legacy_alias_match):
            continue
        row_confidence_label, row_confidence_detail = _company_observation_confidence(
            current_entity_id=entity_id,
            observation_entity_id=row.entity_id,
            observation_raw_name=row.raw_name,
            canonical_name=entity.canonical_name,
            normalized_aliases=normalized_aliases,
            entity_confidence_label=entity_confidence_label,
            entity_confidence_detail=entity_confidence_detail,
        )
        observation = CompanyObservationReadModel(
            holding_id=int(row.holding_id),
            raw_name=row.raw_name,
            source_file_id=row.source_file_id,
            source_row_number=row.source_row_number,
            fund_code=row.fund_code,
            fund_name=row.fund_name,
            option_code=row.option_code,
            option_name=row.option_name,
            reporting_period_end_date=row.reporting_period_end_date,
            canonical_asset_class_code=row.canonical_asset_class_code,
            source_asset_class_raw=row.source_asset_class_raw,
            source_subclass_raw=row.source_subclass_raw,
            disclosure_completeness=row.disclosure_completeness,
            value_aud=row.value_aud,
            ownership_pct=row.ownership_pct,
            value_band_raw=row.value_band_raw,
            currency_raw=row.currency_raw,
            disclosure_label=_humanize_disclosure_completeness(row.disclosure_completeness),
            confidence_label=row_confidence_label,
            confidence_detail=row_confidence_detail,
            is_value_band=row.value_band_raw is not None,
        )
        if is_manager_role:
            manager_role_rows.append(observation)
        if is_direct_holding or is_legacy_alias_match:
            direct_holding_rows.append(observation)
        if is_issuer_role:
            issuer_role_rows.append(observation)

    observations = _unique_observations_by_holding_id(
        [*manager_role_rows, *direct_holding_rows, *issuer_role_rows],
    )

    latest_reporting_period = max(
        (observation.reporting_period_end_date for observation in observations),
        default=None,
    )

    period_history_counts: dict[date, dict[str, object]] = {}
    for observation in observations:
        period_bucket = period_history_counts.setdefault(
            observation.reporting_period_end_date,
            {
                "observation_count": 0,
                "fund_codes": set(),
            },
        )
        period_bucket["observation_count"] = int(period_bucket["observation_count"]) + 1
        period_bucket["fund_codes"].add(observation.fund_code)

    period_history = [
        CompanyPeriodHistoryReadModel(
            reporting_period_end_date=period_end_date,
            observation_count=int(period_bucket["observation_count"]),
            fund_count=len(period_bucket["fund_codes"]),
        )
        for period_end_date, period_bucket in sorted(period_history_counts.items(), reverse=True)
    ]

    history_is_limited = len(period_history) <= 1
    history_note = (
        "Only one reporting period is currently available for this canonical company detail slice."
        if history_is_limited
        else None
    )
    holder_slice_count = len(
        {
            (observation.fund_code, observation.option_code, observation.reporting_period_end_date)
            for observation in observations
        }
    )
    disclosure_counter = Counter(observation.disclosure_completeness for observation in observations)
    disclosure_summary = [
        (_humanize_disclosure_completeness(disclosure_key), disclosure_counter[disclosure_key])
        for disclosure_key in sorted(
            disclosure_counter,
            key=lambda item: DISCLOSURE_COMPLETENESS_SORT_ORDER.get(item, 999),
        )
    ]
    primary_observations = [observation for observation in observations if not observation.is_value_band]
    value_band_observations = [observation for observation in observations if observation.is_value_band]

    return CompanyDetailReadModel(
        entity_id=entity.id,
        canonical_name=entity.canonical_name,
        entity_type=entity.entity_type,
        abn=entity.abn,
        abn_review_source=entity.abn_review_source,
        abn_reviewed_by=entity.abn_reviewed_by,
        abn_reviewed_at=entity.abn_reviewed_at,
        registered_name_on_abr=entity.registered_name_on_abr,
        acn=entity.acn,
        asic_company_status=entity.asic_company_status,
        asic_company_type=entity.asic_company_type,
        asic_registration_date=entity.asic_registration_date,
        asic_next_review_date=entity.asic_next_review_date,
        asic_record_url=entity.asic_record_url,
        asic_review_source=entity.asic_review_source,
        asic_reviewed_by=entity.asic_reviewed_by,
        asic_reviewed_at=entity.asic_reviewed_at,
        aliases=aliases,
        matched_raw_names=sorted({observation.raw_name for observation in observations}),
        asset_classes=sorted({observation.canonical_asset_class_code for observation in observations}),
        relationships=relationships,
        observation_count=len(observations),
        fund_count=len({observation.fund_code for observation in observations}),
        holder_slice_count=holder_slice_count,
        latest_reporting_period=latest_reporting_period,
        history_is_limited=history_is_limited,
        history_note=history_note,
        resolution_scope_note=(
            "Only linked holdings and exact seeded aliases are included here; unresolved raw-name variants remain "
            "outside the canonical company view until current stored truth supports linking them."
        ),
        entity_confidence_label=entity_confidence_label,
        entity_confidence_detail=entity_confidence_detail,
        disclosure_summary=disclosure_summary,
        period_history=period_history,
        observations=observations,
        manager_role_rows=manager_role_rows,
        direct_holding_rows=direct_holding_rows,
        issuer_role_rows=issuer_role_rows,
        primary_observations=primary_observations,
        value_band_observations=value_band_observations,
    )


DISCLOSURE_COMPLETENESS_SORT_ORDER = {
    "fully_disclosed": 0,
    "value_only": 1,
    "ownership_only": 2,
    "name_only": 3,
    "aggregate_total": 4,
}

DISCLOSURE_COMPLETENESS_LABELS = {
    "fully_disclosed": "Direct",
    "value_only": "Value only",
    "ownership_only": "Ownership only",
    "name_only": "Name only",
    "aggregate_total": "Section total",
}

PRIVATE_ASSET_CLASS_CODES = {
    "private_debt",
    "unlisted_equity",
    "unlisted_infrastructure",
    "unlisted_property",
}

SEARCH_KIND_LABELS = {
    "company": "Company",
    "fund": "Fund",
    "manager": "Manager",
}

SEARCH_FILTER_LABELS = {
    "all": "All results",
    "company": "Companies",
    "fund": "Funds",
    "manager": "Managers",
}

SEARCH_KIND_SORT_ORDER = {
    "fund": 0,
    "company": 1,
    "manager": 2,
}

SEARCH_MATCH_LABELS = {
    "alias": "Alias",
    "canonical_name": "Canonical name",
    "fund_code": "Fund code",
    "fund_name": "Fund name",
}

SEARCH_MATCH_SOURCE_PRIORITY = {
    "fund_code": 240,
    "canonical_name": 200,
    "fund_name": 180,
    "alias": 160,
}

DEMO_ENTITY_TYPE_LABELS = {
    "all": "All entity types",
    "company": "Companies",
    "manager": "Managers",
    "asset": "Assets",
    "fund_vehicle": "Fund vehicles",
    "property_asset": "Property assets",
    "infrastructure_asset": "Infrastructure assets",
}

DEMO_ENTITY_SORT_LABELS = {
    "value_aud_desc": "Total disclosed value",
    "fund_count_desc": "Funds",
    "option_count_desc": "Options",
    "row_count_desc": "Rows",
    "ownership_count_desc": "Ownership disclosures",
}

DEMO_DISCLOSURE_MIX_KEYS = (
    "fully_disclosed",
    "value_only",
    "ownership_only",
    "name_only",
)


def get_fund_detail(
    session: Session,
    *,
    fund_code: str,
) -> FundDetailReadModel | None:
    lookup_code = fund_code.strip()
    if lookup_code == "":
        raise ValueError("fund_code must not be blank")

    fund = session.scalar(select(Fund).where(func.lower(Fund.code) == lookup_code.casefold()))
    if fund is None:
        return None

    option_rows = session.execute(
        select(
            InvestmentOption.id,
            InvestmentOption.source_option_code,
            InvestmentOption.source_option_name,
        )
        .where(InvestmentOption.fund_id == fund.id)
        .order_by(InvestmentOption.source_option_name.asc(), InvestmentOption.id.asc())
    ).all()

    holding_rows = session.execute(
        select(
            Holding.raw_name,
            Holding.entity_id,
            Holding.source_file_id,
            Holding.source_row_number,
            Holding.disclosure_completeness,
            Holding.value_aud,
            Holding.ownership_pct,
            Holding.value_band_raw,
            Holding.source_asset_class_raw,
            Holding.source_subclass_raw,
            Holding.classification_raw,
            CanonicalAssetClass.code.label("canonical_asset_class_code"),
            Entity.canonical_name.label("entity_canonical_name"),
            Entity.entity_type.label("entity_type"),
            Entity.confidence_tier.label("entity_confidence_tier"),
            InvestmentOption.id.label("option_id"),
            InvestmentOption.source_option_code.label("option_code"),
            InvestmentOption.source_option_name.label("option_name"),
            ReportingPeriod.period_end_date.label("reporting_period_end_date"),
        )
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
        .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
        .join(SourceFile, SourceFile.id == Holding.source_file_id)
        .outerjoin(Entity, Entity.id == Holding.entity_id)
        .where(
            Holding.source_fund_id == fund.id,
            Holding.is_aggregate.is_(False),
            Holding.raw_name.is_not(None),
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
        )
        .order_by(
            ReportingPeriod.period_end_date.desc(),
            InvestmentOption.source_option_name.asc(),
            Holding.source_row_number.asc(),
        )
    ).all()

    observed_periods = sorted({row.reporting_period_end_date for row in holding_rows}, reverse=True)
    latest_reporting_period = observed_periods[0] if observed_periods else None
    prior_reporting_period = observed_periods[1] if len(observed_periods) > 1 else None
    current_rows = (
        [row for row in holding_rows if row.reporting_period_end_date == latest_reporting_period]
        if latest_reporting_period is not None
        else []
    )

    current_rows_by_option_id: dict[int, list[object]] = {}
    for row in current_rows:
        current_rows_by_option_id.setdefault(int(row.option_id), []).append(row)

    investment_options: list[FundInvestmentOptionReadModel] = []
    for option_row in option_rows:
        option_specific_rows = current_rows_by_option_id.get(int(option_row.id), [])
        asset_mix_buckets: dict[tuple[str, str], dict[str, object]] = {}
        top_direct_private_holdings: list[FundObservationSummaryReadModel] = []
        manager_level_aggregate_exposures: list[FundObservationSummaryReadModel] = []
        named_private_exposures: list[FundObservationSummaryReadModel] = []
        value_band_exposures: list[FundObservationSummaryReadModel] = []
        other_named_private_exposures: list[FundObservationSummaryReadModel] = []

        for row in option_specific_rows:
            observation_kind = _derive_fund_observation_kind(
                entity_type=row.entity_type,
                disclosure_completeness=row.disclosure_completeness,
                ownership_pct=row.ownership_pct,
                source_subclass_raw=row.source_subclass_raw,
                classification_raw=row.classification_raw,
            )
            if row.entity_canonical_name is not None:
                confidence_label, confidence_detail = _company_entity_confidence(
                    confidence_tier=row.entity_confidence_tier,
                )
            else:
                confidence_label, confidence_detail = (
                    "Unresolved",
                    "This observation is not currently linked to a canonical entity in stored truth.",
                )
            summary = FundObservationSummaryReadModel(
                raw_name=row.raw_name,
                entity_id=row.entity_id,
                entity_canonical_name=row.entity_canonical_name,
                entity_type=row.entity_type,
                source_file_id=row.source_file_id,
                source_row_number=row.source_row_number,
                reporting_period_end_date=row.reporting_period_end_date,
                canonical_asset_class_code=row.canonical_asset_class_code,
                source_asset_class_raw=row.source_asset_class_raw,
                source_subclass_raw=row.source_subclass_raw,
                classification_raw=row.classification_raw,
                disclosure_completeness=row.disclosure_completeness,
                observation_kind=observation_kind,
                value_aud=row.value_aud,
                ownership_pct=row.ownership_pct,
                value_band_raw=row.value_band_raw,
                disclosure_label=_humanize_disclosure_completeness(row.disclosure_completeness),
                observation_kind_label=_humanize_observation_kind(observation_kind),
                confidence_label=confidence_label,
                confidence_detail=confidence_detail,
            )

            bucket_key = (row.canonical_asset_class_code, row.disclosure_completeness)
            bucket = asset_mix_buckets.setdefault(
                bucket_key,
                {
                    "observation_count": 0,
                    "precise_value_row_count": 0,
                    "precise_value_aud_total": Decimal("0"),
                },
            )
            bucket["observation_count"] = int(bucket["observation_count"]) + 1
            if row.value_aud is not None:
                bucket["precise_value_row_count"] = int(bucket["precise_value_row_count"]) + 1
                bucket["precise_value_aud_total"] = Decimal(bucket["precise_value_aud_total"]) + row.value_aud

            if summary.canonical_asset_class_code in PRIVATE_ASSET_CLASS_CODES:
                if observation_kind == "direct_holding":
                    top_direct_private_holdings.append(summary)
                elif observation_kind == "unknown":
                    named_private_exposures.append(summary)
                    if summary.value_band_raw is not None:
                        value_band_exposures.append(summary)
                    else:
                        other_named_private_exposures.append(summary)

            if observation_kind == "manager_rollup":
                manager_level_aggregate_exposures.append(summary)

        mix_by_asset_class: dict[str, list[FundAssetClassMixBucketReadModel]] = {}
        for (asset_class_code, disclosure_completeness), bucket in asset_mix_buckets.items():
            mix_by_asset_class.setdefault(asset_class_code, []).append(
                FundAssetClassMixBucketReadModel(
                    disclosure_completeness=disclosure_completeness,
                    observation_count=int(bucket["observation_count"]),
                    precise_value_row_count=int(bucket["precise_value_row_count"]),
                    precise_value_aud_total=Decimal(bucket["precise_value_aud_total"]),
                )
            )

        investment_options.append(
            FundInvestmentOptionReadModel(
                option_id=int(option_row.id),
                option_code=option_row.source_option_code,
                option_name=option_row.source_option_name,
                reporting_period_end_date=latest_reporting_period,
                observation_count=len(option_specific_rows),
                asset_class_mix=[
                    FundAssetClassMixReadModel(
                        canonical_asset_class_code=asset_class_code,
                        by_disclosure_completeness=sorted(
                            buckets,
                            key=lambda item: DISCLOSURE_COMPLETENESS_SORT_ORDER.get(
                                item.disclosure_completeness,
                                999,
                            ),
                        ),
                    )
                    for asset_class_code, buckets in sorted(mix_by_asset_class.items(), key=lambda item: item[0])
                ],
                top_direct_private_holdings=sorted(
                    top_direct_private_holdings,
                    key=_fund_observation_sort_key,
                )[:10],
                manager_level_aggregate_exposures=sorted(
                    manager_level_aggregate_exposures,
                    key=_fund_observation_sort_key,
                )[:10],
                named_private_exposures=sorted(
                    named_private_exposures,
                    key=_fund_observation_sort_key,
                )[:10],
                value_band_exposures=sorted(
                    value_band_exposures,
                    key=_fund_observation_sort_key,
                )[:10],
                other_named_private_exposures=sorted(
                    other_named_private_exposures,
                    key=_fund_observation_sort_key,
                )[:10],
            )
        )

    return FundDetailReadModel(
        fund_id=fund.id,
        fund_code=fund.code,
        fund_name=fund.name,
        latest_reporting_period=latest_reporting_period,
        investment_options=investment_options,
        change_since_prior_reporting_period=FundChangeReadModel(
            available=False,
            current_reporting_period_end_date=latest_reporting_period,
            prior_reporting_period_end_date=prior_reporting_period,
            note=(
                "Only one reporting period is currently available for this fund detail slice."
                if prior_reporting_period is None
                else "Change since prior reporting period is not yet exposed on the fund detail slice."
            ),
        ),
    )


def get_australiansuper_stable_matched_asset_proof(session: Session) -> MatchedAssetProofReadModel:
    rows = session.execute(
        select(
            Entity.id.label("asset_entity_id"),
            Entity.canonical_name.label("asset_entity_name"),
            Entity.entity_type,
            Fund.code.label("source_fund_code"),
            Fund.name.label("source_fund_name"),
            InvestmentOption.source_option_code.label("option_code"),
            InvestmentOption.source_option_name.label("option_name"),
            ReportingPeriod.period_end_date.label("reporting_period_end_date"),
            CanonicalAssetClass.code.label("canonical_asset_class_code"),
            Holding.source_asset_class_raw,
            Holding.source_subclass_raw,
            Holding.disclosure_completeness,
            Holding.ownership_pct,
            Holding.value_band_raw,
            Holding.classification_raw,
            Holding.address,
            Holding.location_raw,
            Holding.geo_lat,
            Holding.geo_lng,
            HoldingRelationship.confidence_score,
            HoldingRelationship.source.label("relationship_source"),
            Holding.source_file_id,
            Holding.source_row_number,
            Holding.metadata_attached_from_row_numbers,
        )
        .join(Holding, Holding.id == HoldingRelationship.holding_id)
        .join(Entity, Entity.id == HoldingRelationship.related_entity_id)
        .join(Fund, Fund.id == Holding.source_fund_id)
        .join(InvestmentOption, InvestmentOption.id == Holding.source_option_id)
        .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
        .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
        .join(SourceFile, SourceFile.id == Holding.source_file_id)
        .where(
            HoldingRelationship.relationship_role == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_RELATIONSHIP_ROLE,
            HoldingRelationship.source == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE,
            Holding.source_row_number.in_(AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGET_ROW_NUMBERS),
            Fund.code == "australiansuper",
            SourceFile.adapter_key == "AustralianSuperPhdAdapter",
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
            InvestmentOption.source_option_code == "ARST",
            InvestmentOption.source_option_name == "Stable",
        )
        .order_by(Holding.source_row_number.asc())
    ).all()

    proof_rows = [
        MatchedAssetProofRowReadModel(
            asset_entity_id=row.asset_entity_id,
            asset_entity_name=row.asset_entity_name,
            entity_type=row.entity_type,
            source_fund_code=row.source_fund_code,
            source_fund_name=row.source_fund_name,
            option_code=row.option_code,
            option_name=row.option_name,
            reporting_period_end_date=row.reporting_period_end_date,
            canonical_asset_class_code=row.canonical_asset_class_code,
            source_asset_class_raw=row.source_asset_class_raw,
            source_subclass_raw=row.source_subclass_raw,
            disclosure_completeness=row.disclosure_completeness,
            ownership_pct=row.ownership_pct,
            value_band_raw=row.value_band_raw,
            classification_raw=row.classification_raw,
            address=row.address,
            location_raw=row.location_raw,
            geo_lat=row.geo_lat,
            geo_lng=row.geo_lng,
            confidence_score=row.confidence_score,
            relationship_source=row.relationship_source,
            source_file_id=row.source_file_id,
            source_row_number=row.source_row_number,
            metadata_attached_from_row_numbers=list(row.metadata_attached_from_row_numbers or []),
        )
        for row in rows
    ]
    return MatchedAssetProofReadModel(
        proof_key=AUSTRALIANSUPER_STABLE_MATCHED_ASSET_PROOF_KEY,
        title="Experimental seven-row coordinate proof",
        scope_note=(
            "Bounded rendering proof using stored coordinates from AustralianSuper Stable disclosures. "
            "Not a full property or infrastructure map."
        ),
        matched_asset_count=len(proof_rows),
        rows=proof_rows,
    )


def search_entities_and_funds(
    session: Session,
    *,
    query: str,
    limit: int = 20,
    kind: str = "all",
) -> SearchResultsReadModel:
    lookup_query = query.strip()
    if lookup_query == "":
        raise ValueError("query must not be blank")
    active_kind = _normalise_search_kind(kind)

    normalized_query = normalise_name(lookup_query)
    if normalized_query == "":
        return SearchResultsReadModel(
            query=lookup_query,
            normalized_query=normalized_query,
            active_kind=active_kind,
            result_count=0,
            total_result_count=0,
            kind_counts={search_kind: 0 for search_kind in SEARCH_FILTER_LABELS},
            results=[],
        )

    query_casefold = lookup_query.casefold()
    scored_results: list[tuple[int, SearchResultReadModel]] = []

    fund_rows = session.execute(
        select(
            Fund.code,
            Fund.name,
        ).order_by(Fund.name.asc(), Fund.code.asc())
    ).all()
    for row in fund_rows:
        best_match = _best_search_candidate(
            query_casefold=query_casefold,
            normalized_query=normalized_query,
            candidates=(
                ("fund_code", row.code),
                ("fund_name", row.name),
            ),
        )
        if best_match is None:
            continue
        score, matched_on, matched_value = best_match
        scored_results.append(
            (
                score,
                SearchResultReadModel(
                    result_kind="fund",
                    result_kind_label=SEARCH_KIND_LABELS["fund"],
                    title=row.name,
                    matched_on=matched_on,
                    matched_on_label=SEARCH_MATCH_LABELS[matched_on],
                    matched_value=matched_value,
                    entity_id=None,
                    fund_code=row.code,
                ),
            )
        )

    entity_rows = session.execute(
        select(
            Entity.id,
            Entity.entity_type,
            Entity.canonical_name,
            EntityAlias.alias,
        )
        .outerjoin(EntityAlias, EntityAlias.entity_id == Entity.id)
        .where(Entity.entity_type.in_(("company", "manager")))
        .order_by(
            Entity.entity_type.asc(),
            Entity.canonical_name.asc(),
            EntityAlias.is_preferred.desc(),
            EntityAlias.alias.asc(),
        )
    ).all()

    entities_by_id: dict[int, dict[str, object]] = {}
    for row in entity_rows:
        entity_bucket = entities_by_id.setdefault(
            int(row.id),
            {
                "entity_type": row.entity_type,
                "canonical_name": row.canonical_name,
                "aliases": [],
            },
        )
        if row.alias is not None:
            aliases = entity_bucket["aliases"]
            if row.alias not in aliases:
                aliases.append(row.alias)

    for entity_id, entity_bucket in entities_by_id.items():
        entity_type = str(entity_bucket["entity_type"])
        canonical_name = str(entity_bucket["canonical_name"])
        aliases = [str(alias) for alias in entity_bucket["aliases"]]
        best_match = _best_search_candidate(
            query_casefold=query_casefold,
            normalized_query=normalized_query,
            candidates=[("canonical_name", canonical_name), *[("alias", alias) for alias in aliases]],
        )
        if best_match is None:
            continue
        score, matched_on, matched_value = best_match
        scored_results.append(
            (
                score,
                SearchResultReadModel(
                    result_kind=entity_type,
                    result_kind_label=SEARCH_KIND_LABELS[entity_type],
                    title=canonical_name,
                    matched_on=matched_on,
                    matched_on_label=SEARCH_MATCH_LABELS[matched_on],
                    matched_value=matched_value,
                    entity_id=entity_id,
                    fund_code=None,
                ),
            )
        )

    scored_results.sort(
        key=lambda item: (
            -item[0],
            SEARCH_KIND_SORT_ORDER.get(item[1].result_kind, 999),
            item[1].title.casefold(),
            item[1].matched_value.casefold(),
        )
    )
    all_results = [item for _, item in scored_results]
    kind_counts = {
        "all": len(all_results),
        **{
            search_kind: sum(1 for item in all_results if item.result_kind == search_kind)
            for search_kind in SEARCH_KIND_LABELS
        },
    }
    filtered_results = (
        [item for item in all_results if item.result_kind == active_kind]
        if active_kind != "all"
        else all_results
    )
    results = filtered_results[:limit]
    return SearchResultsReadModel(
        query=lookup_query,
        normalized_query=normalized_query,
        active_kind=active_kind,
        result_count=len(results),
        total_result_count=len(all_results),
        kind_counts=kind_counts,
        results=results,
    )


def get_homepage(session: Session) -> HomepageReadModel:
    period_dates = session.scalars(
        select(ReportingPeriod.period_end_date)
        .join(SourceFile, SourceFile.reporting_period_id == ReportingPeriod.id)
        .where(
            SourceFile.reporting_period_id.is_not(None),
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
        )
        .distinct()
        .order_by(ReportingPeriod.period_end_date.desc())
    ).all()

    latest_reporting_period = period_dates[0] if period_dates else None
    prior_reporting_period = period_dates[1] if len(period_dates) > 1 else None

    corpus_stats = _get_homepage_corpus_stats(session)
    change_available = prior_reporting_period is not None

    featured_company = session.scalar(
        select(Entity).where(
            Entity.entity_type == "company",
            Entity.canonical_name == "Industry Super Holdings Pty Ltd",
        )
    )
    featured_manager = session.scalar(
        select(Entity).where(
            Entity.entity_type == "manager",
            Entity.canonical_name == "IFM Investors Pty Ltd",
        )
    )

    return HomepageReadModel(
        latest_reporting_period=latest_reporting_period,
        prior_reporting_period=prior_reporting_period,
        change_available=change_available,
        change_note=(
            "Current-period counts are compared with the prior loaded reporting period."
            if change_available
            else (
                f"Latest period loaded: {_format_homepage_period(latest_reporting_period)}. "
                "Change tracking unlocks once a second reporting period is loaded."
            )
        ),
        stats=[
            HomepageStatReadModel(label="Funds loaded", value=corpus_stats["funds_loaded"]),
            HomepageStatReadModel(label="Source files loaded", value=corpus_stats["source_files_loaded"]),
            HomepageStatReadModel(label="Holding rows loaded", value=corpus_stats["holding_rows_loaded"]),
            HomepageStatReadModel(
                label="Reviewed companies",
                value=corpus_stats["reviewed_companies"],
                note="Reviewed canonical entities linked to loaded holdings",
            ),
            HomepageStatReadModel(
                label="Reviewed managers",
                value=corpus_stats["reviewed_managers"],
                note="Reviewed canonical entities linked to loaded holdings",
            ),
            HomepageStatReadModel(
                label="Latest reporting period",
                value=_format_homepage_period(latest_reporting_period),
            ),
        ],
        change_metrics=[],
        featured_entries=[
            HomepageFeatureEntryReadModel(
                kicker="Named private company ownership",
                title=(
                    featured_company.canonical_name
                    if featured_company is not None
                    else "Direct private company ownership index"
                ),
                deck=(
                    "Lead with a company view that preserves per-fund disclosure variance, completeness states, "
                    "and the rule that cross-fund totals are never silently computed."
                ),
                result_kind="company",
                entity_id=(featured_company.id if featured_company is not None else None),
                fund_code=None,
                search_query=("Industry Super Holdings" if featured_company is None else None),
                cta_label="Open company",
                status_label="Live now",
            ),
            HomepageFeatureEntryReadModel(
                kicker="Manager exposure view",
                title=(
                    featured_manager.canonical_name
                    if featured_manager is not None
                    else "Manager exposure surface"
                ),
                deck=(
                    "Use the manager page to separate manager rollups from owned issuers and keep disclosure limits "
                    "useful instead of flattening them into one blended exposure story."
                ),
                result_kind="manager",
                entity_id=(featured_manager.id if featured_manager is not None else None),
                fund_code=None,
                search_query=("IFM Investors" if featured_manager is None else None),
                cta_label="Open manager",
                status_label="Live now",
            ),
            HomepageFeatureEntryReadModel(
                kicker="Mapped property and infrastructure assets",
                title="AustralianSuper Stable matched-asset map proof",
                deck=(
                    "A bounded seven-row AustralianSuper Stable map proof now displays matched property and "
                    "infrastructure assets with coordinates, confidence, and source-row provenance. It is not "
                    "comprehensive national, cross-fund, or Cbus map coverage."
                ),
                result_kind="matched_asset_proof",
                entity_id=None,
                fund_code=None,
                search_query=None,
                cta_label="Open matched-asset proof",
                status_label="Seven-row proof live",
            ),
        ],
        editorial_note=(
            "Disclosure completeness is the core rule of the product. Some rows give precise values, some give "
            "ownership only, some disclose a value band, and some name an exposure without a precise amount. "
            "That unevenness is a feature to interpret carefully, not noise to smooth away."
        ),
    )


def get_demo_dashboard(session: Session) -> DemoDashboardReadModel:
    ifm_entity = _find_demo_entity(
        session,
        canonical_name="IFM Investors Pty Ltd",
        entity_type="manager",
    )
    industry_super_entity = _find_demo_entity(
        session,
        canonical_name="Industry Super Holdings Pty Ltd",
        entity_type="company",
    )

    curated_links = [
        DemoCuratedLinkReadModel(
            title="IFM Investors",
            deck="Manager detail with manager-role, held-entity, and issuer-role rows kept separate.",
            result_kind="manager",
            entity_id=ifm_entity.id if ifm_entity is not None else None,
            search_query="IFM Investors",
            cta_label="Open manager",
            status_label="Manager",
        ),
        DemoCuratedLinkReadModel(
            title="Industry Super Holdings",
            deck="Company detail showing cross-fund disclosure variance without rolling it into a silent total.",
            result_kind="company",
            entity_id=industry_super_entity.id if industry_super_entity is not None else None,
            search_query="Industry Super Holdings",
            cta_label="Open company",
            status_label="Company",
        ),
        DemoCuratedLinkReadModel(
            title="RUMIN8",
            deck="Aware ownership_only example; use search when the current corpus has no reviewed canonical entity.",
            result_kind="search",
            entity_id=None,
            search_query="RUMIN8",
            cta_label="Search RUMIN8",
            status_label="ownership_only example",
        ),
        DemoCuratedLinkReadModel(
            title="FSSSP",
            deck="Aware 100% ownership example; search keeps the row-level disclosure state visible.",
            result_kind="search",
            entity_id=None,
            search_query="FSSSP",
            cta_label="Search FSSSP",
            status_label="100% ownership example",
        ),
    ]

    if _demo_name_exists_in_current_corpus(session, "HARRISON AI"):
        curated_links.append(
            DemoCuratedLinkReadModel(
                title="HARRISON AI",
                deck="Optional current-corpus example, shown only when the loaded corpus contains it.",
                result_kind="search",
                entity_id=None,
                search_query="HARRISON AI",
                cta_label="Search HARRISON AI",
                status_label="Present in corpus",
            )
        )

    curated_links.append(
        DemoCuratedLinkReadModel(
            title="Experimental seven-row coordinate proof",
            deck="Experimental seven-row coordinate proof — not full coverage.",
            result_kind="matched_asset_proof",
            entity_id=None,
            search_query=None,
            cta_label="Open proof",
            status_label="Experimental",
        )
    )

    return DemoDashboardReadModel(
        homepage=get_homepage(session),
        curated_links=curated_links,
    )


def get_demo_entity_explorer(
    session: Session,
    *,
    entity_type: str = "all",
    disclosure_completeness: list[str] | None = None,
    fund: list[str] | None = None,
    canonical_asset_class: list[str] | None = None,
    sort: str = "value_aud_desc",
    page: int = 1,
    page_size: int = 50,
) -> DemoEntityExplorerReadModel:
    active_entity_type = entity_type.strip() if entity_type else "all"
    if active_entity_type not in DEMO_ENTITY_TYPE_LABELS:
        raise ValueError(f"Unknown entity type filter: {active_entity_type}")
    if sort not in DEMO_ENTITY_SORT_LABELS:
        raise ValueError(f"Unknown entity explorer sort key: {sort}")
    if page < 1:
        raise ValueError("page must be greater than or equal to 1")

    selected_disclosures = _clean_demo_filter_values(disclosure_completeness)
    unknown_disclosures = set(selected_disclosures) - set(DISCLOSURE_COMPLETENESS_SORT_ORDER)
    if unknown_disclosures:
        raise ValueError(f"Unknown disclosure completeness filter: {sorted(unknown_disclosures)[0]}")
    selected_funds = _clean_demo_filter_values(fund)
    selected_asset_classes = _clean_demo_filter_values(canonical_asset_class)

    holding_rows = _load_demo_current_nonaggregate_rows(
        session,
        disclosure_completeness=selected_disclosures,
        fund_codes=selected_funds,
    )
    role_entity_ids = {
        entity_id
        for row in holding_rows
        for entity_id in (row.entity_id, row.manager_entity_id, row.issuer_entity_id)
        if entity_id is not None
    }
    entities_by_id = {
        entity.id: entity
        for entity in session.scalars(select(Entity).where(Entity.id.in_(role_entity_ids))).all()
    } if role_entity_ids else {}

    buckets: dict[int, dict[str, object]] = {}
    selected_asset_class_set = set(selected_asset_classes)
    for row in holding_rows:
        asset_class_value = row.canonical_asset_class_code or row.source_asset_class_raw
        if selected_asset_class_set and asset_class_value not in selected_asset_class_set:
            continue

        row_entity_ids = {
            entity_id
            for entity_id in (row.entity_id, row.manager_entity_id, row.issuer_entity_id)
            if entity_id is not None
        }
        for entity_id in row_entity_ids:
            entity = entities_by_id.get(entity_id)
            if entity is None:
                continue
            if active_entity_type != "all" and entity.entity_type != active_entity_type:
                continue

            bucket = buckets.setdefault(
                entity_id,
                {
                    "entity": entity,
                    "fund_ids": set(),
                    "option_ids": set(),
                    "row_count": 0,
                    "total_value_aud": Decimal("0"),
                    "ownership_count": 0,
                    "disclosure_counts": Counter(),
                },
            )
            bucket["fund_ids"].add(row.source_fund_id)
            bucket["option_ids"].add(row.source_option_id)
            bucket["row_count"] = int(bucket["row_count"]) + 1
            if row.value_aud is not None:
                bucket["total_value_aud"] = bucket["total_value_aud"] + row.value_aud
            if row.ownership_pct is not None:
                bucket["ownership_count"] = int(bucket["ownership_count"]) + 1
            bucket["disclosure_counts"][row.disclosure_completeness] += 1

    explorer_rows = [
        DemoEntityExplorerRowReadModel(
            entity_id=entity_id,
            entity_name=bucket["entity"].canonical_name,
            entity_type=bucket["entity"].entity_type,
            fund_count=len(bucket["fund_ids"]),
            option_count=len(bucket["option_ids"]),
            row_count=int(bucket["row_count"]),
            total_value_aud=bucket["total_value_aud"],
            ownership_count=int(bucket["ownership_count"]),
            disclosure_mix=[
                (key, int(bucket["disclosure_counts"].get(key, 0)))
                for key in DEMO_DISCLOSURE_MIX_KEYS
                if int(bucket["disclosure_counts"].get(key, 0)) > 0
            ],
        )
        for entity_id, bucket in buckets.items()
    ]
    explorer_rows.sort(key=lambda row: _demo_entity_sort_key(row, sort))

    total_rows = len(explorer_rows)
    total_pages = max(1, math.ceil(total_rows / page_size))
    page_start = (page - 1) * page_size
    page_end = page_start + page_size

    return DemoEntityExplorerReadModel(
        rows=explorer_rows[page_start:page_end],
        total_rows=total_rows,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        sort=sort,
        active_entity_type=active_entity_type,
        selected_disclosure_completeness=selected_disclosures,
        selected_funds=selected_funds,
        selected_asset_classes=selected_asset_classes,
        sort_options=[
            DemoEntityExplorerFilterOption(value=value, label=label)
            for value, label in DEMO_ENTITY_SORT_LABELS.items()
        ],
        entity_type_options=[
            DemoEntityExplorerFilterOption(value=value, label=label)
            for value, label in DEMO_ENTITY_TYPE_LABELS.items()
        ],
        disclosure_options=[
            DemoEntityExplorerFilterOption(value=value, label=_humanize_disclosure_completeness(value))
            for value in DISCLOSURE_COMPLETENESS_SORT_ORDER
        ],
        fund_options=_get_demo_fund_filter_options(session),
        asset_class_options=_get_demo_asset_class_filter_options(session),
    )


def _find_demo_entity(
    session: Session,
    *,
    canonical_name: str,
    entity_type: str,
) -> Entity | None:
    return session.scalar(
        select(Entity).where(
            Entity.entity_type == entity_type,
            Entity.canonical_name == canonical_name,
        )
    )


def _demo_name_exists_in_current_corpus(session: Session, name: str) -> bool:
    lookup = name.strip().casefold()
    if lookup == "":
        return False
    lookup_normalized = normalise_name(name)
    leading_token = lookup.split()[0]
    candidate_names = session.scalars(
        select(Holding.raw_name)
        .join(SourceFile, SourceFile.id == Holding.source_file_id)
        .where(
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
            Holding.raw_name.is_not(None),
            func.lower(Holding.raw_name).like(f"%{leading_token}%"),
        )
    ).all()
    return any(
        lookup_normalized == normalise_name(raw_name)
        or lookup_normalized in normalise_name(raw_name)
        or lookup in raw_name.casefold()
        for raw_name in candidate_names
        if raw_name
    )


def _clean_demo_filter_values(values: list[str] | str | None) -> list[str]:
    if values is None:
        return []
    raw_values = [values] if isinstance(values, str) else values
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        cleaned_value = str(value).strip()
        if cleaned_value == "" or cleaned_value in seen:
            continue
        cleaned.append(cleaned_value)
        seen.add(cleaned_value)
    return cleaned


def _load_demo_current_nonaggregate_rows(
    session: Session,
    *,
    disclosure_completeness: list[str],
    fund_codes: list[str],
):
    statement = (
        select(
            Holding.id.label("holding_id"),
            Holding.entity_id,
            Holding.manager_entity_id,
            Holding.issuer_entity_id,
            Holding.source_fund_id,
            Holding.source_option_id,
            Holding.disclosure_completeness,
            Holding.value_aud,
            Holding.ownership_pct,
            Holding.source_asset_class_raw,
            CanonicalAssetClass.code.label("canonical_asset_class_code"),
        )
        .join(SourceFile, SourceFile.id == Holding.source_file_id)
        .join(Fund, Fund.id == Holding.source_fund_id)
        .outerjoin(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
        .where(
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
            Holding.is_aggregate.is_(False),
        )
    )
    if disclosure_completeness:
        statement = statement.where(Holding.disclosure_completeness.in_(disclosure_completeness))
    if fund_codes:
        statement = statement.where(Fund.code.in_(fund_codes))
    return session.execute(statement).all()


def _get_demo_fund_filter_options(session: Session) -> list[DemoEntityExplorerFilterOption]:
    rows = session.execute(
        select(Fund.code, Fund.name)
        .join(SourceFile, SourceFile.fund_id == Fund.id)
        .where(
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
        )
        .distinct()
        .order_by(Fund.name.asc(), Fund.code.asc())
    ).all()
    return [
        DemoEntityExplorerFilterOption(value=row.code, label=f"{row.name} ({row.code})")
        for row in rows
    ]


def _get_demo_asset_class_filter_options(session: Session) -> list[DemoEntityExplorerFilterOption]:
    rows = session.execute(
        select(
            CanonicalAssetClass.code.label("canonical_asset_class_code"),
            CanonicalAssetClass.label.label("canonical_asset_class_label"),
            Holding.source_asset_class_raw,
        )
        .join(SourceFile, SourceFile.id == Holding.source_file_id)
        .outerjoin(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
        .where(
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
            Holding.is_aggregate.is_(False),
        )
        .distinct()
    ).all()

    options_by_value: dict[str, str] = {}
    for row in rows:
        value = row.canonical_asset_class_code or row.source_asset_class_raw
        label = row.canonical_asset_class_label or row.source_asset_class_raw
        if value and label:
            options_by_value.setdefault(value, label)
    return [
        DemoEntityExplorerFilterOption(value=value, label=label)
        for value, label in sorted(options_by_value.items(), key=lambda item: (item[1].casefold(), item[0]))
    ]


def _demo_entity_sort_key(row: DemoEntityExplorerRowReadModel, sort: str) -> tuple[object, str, int]:
    if sort == "value_aud_desc":
        primary: object = -row.total_value_aud
    elif sort == "fund_count_desc":
        primary = -row.fund_count
    elif sort == "option_count_desc":
        primary = -row.option_count
    elif sort == "row_count_desc":
        primary = -row.row_count
    elif sort == "ownership_count_desc":
        primary = -row.ownership_count
    else:
        raise ValueError(f"Unknown entity explorer sort key: {sort}")
    return (primary, row.entity_name.casefold(), row.entity_id)


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


def _get_entity_aliases(session: Session, *, entity: Entity) -> list[str]:
    alias_rows = session.scalars(
        select(EntityAlias.alias)
        .where(EntityAlias.entity_id == entity.id)
        .order_by(EntityAlias.is_preferred.desc(), EntityAlias.alias.asc())
    ).all()
    return list(dict.fromkeys([entity.canonical_name, *alias_rows]))


def _get_entity_relationships(session: Session, *, entity_id: int) -> list[EntityRelationshipReadModel]:
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
    return [
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


def _get_issuer_holding_ids(session: Session, *, entity_id: int) -> set[int]:
    return {
        int(holding_id)
        for holding_id in session.scalars(
            select(HoldingRelationship.holding_id).where(
                HoldingRelationship.related_entity_id == entity_id,
                HoldingRelationship.relationship_role == "issuer",
            )
        ).all()
    }


def _unique_observations_by_holding_id(observations):
    unique_observations = {}
    for observation in observations:
        unique_observations.setdefault(observation.holding_id, observation)
    return list(unique_observations.values())


def _derive_manager_observation_kind(
    *,
    entity_id: int,
    manager_entity_id: int | None,
    issuer_entity_id: int | None,
    disclosure_completeness: str,
    ownership_pct: Decimal | None,
    source_subclass_raw: str | None,
    classification_raw: str | None,
) -> str:
    if manager_entity_id == entity_id:
        return "manager_rollup"
    if issuer_entity_id == entity_id:
        return "direct_holding"
    if ownership_pct is not None or disclosure_completeness == "fully_disclosed":
        return "direct_holding"
    if source_subclass_raw is not None and normalise_name(source_subclass_raw) == "externally managed":
        return "manager_rollup"
    if classification_raw is not None and "manager" in classification_raw.casefold():
        return "manager_rollup"
    return "unknown"


def _derive_manager_role_classes(
    *,
    manager_role_rows: list[ManagerObservationReadModel],
    direct_holding_rows: list[ManagerObservationReadModel],
    issuer_role_rows: list[ManagerObservationReadModel],
) -> list[str]:
    has_ownership_role = any(
        row.observation_kind == "direct_holding" or row.ownership_pct is not None
        for row in direct_holding_rows
    )
    return [
        role_class
        for role_class, is_present in (
            ("manager", bool(manager_role_rows)),
            ("issuer", bool(issuer_role_rows)),
            ("ownership", has_ownership_role),
        )
        if is_present
    ]


def _build_manager_role_groups(
    rows: list[ManagerObservationReadModel],
) -> list[ManagerRoleFundGroupReadModel]:
    fund_buckets: dict[int, dict[str, object]] = {}
    for row in rows:
        fund_bucket = fund_buckets.setdefault(
            row.source_fund_id,
            {
                "fund_code": row.fund_code,
                "fund_name": row.fund_name,
                "rows": [],
                "option_buckets": {},
            },
        )
        fund_bucket["rows"].append(row)
        option_buckets = fund_bucket["option_buckets"]
        option_bucket = option_buckets.setdefault(
            row.source_option_id,
            {
                "option_code": row.option_code,
                "option_name": row.option_name,
                "rows": [],
            },
        )
        option_bucket["rows"].append(row)

    fund_groups: list[ManagerRoleFundGroupReadModel] = []
    for source_fund_id, fund_bucket in sorted(
        fund_buckets.items(),
        key=lambda item: (str(item[1]["fund_code"]).casefold(), str(item[1]["fund_name"]).casefold()),
    ):
        option_groups = [
            ManagerRoleOptionGroupReadModel(
                source_option_id=source_option_id,
                option_code=str(option_bucket["option_code"]),
                option_name=str(option_bucket["option_name"]),
                row_count=len(option_bucket["rows"]),
                value_aud_total=sum(
                    (row.value_aud for row in option_bucket["rows"] if row.value_aud is not None),
                    Decimal("0"),
                ),
                rows=option_bucket["rows"],
            )
            for source_option_id, option_bucket in sorted(
                fund_bucket["option_buckets"].items(),
                key=lambda item: (str(item[1]["option_name"]).casefold(), str(item[1]["option_code"]).casefold()),
            )
        ]
        fund_groups.append(
            ManagerRoleFundGroupReadModel(
                source_fund_id=source_fund_id,
                fund_code=str(fund_bucket["fund_code"]),
                fund_name=str(fund_bucket["fund_name"]),
                row_count=len(fund_bucket["rows"]),
                value_aud_total=sum(
                    (row.value_aud for row in fund_bucket["rows"] if row.value_aud is not None),
                    Decimal("0"),
                ),
                option_groups=option_groups,
            )
        )

    return fund_groups


def _derive_fund_observation_kind(
    *,
    entity_type: str | None,
    disclosure_completeness: str,
    ownership_pct: Decimal | None,
    source_subclass_raw: str | None,
    classification_raw: str | None,
) -> str:
    if ownership_pct is not None or disclosure_completeness == "fully_disclosed":
        return "direct_holding"
    if entity_type == "manager":
        return "manager_rollup"
    if classification_raw is not None and "manager" in classification_raw.casefold():
        return "manager_rollup"
    if (
        disclosure_completeness == "value_only"
        and source_subclass_raw is not None
        and normalise_name(source_subclass_raw) == "externally managed"
    ):
        return "manager_rollup"
    return "unknown"


def _fund_observation_sort_key(item: FundObservationSummaryReadModel) -> tuple[object, ...]:
    value_rank = item.value_aud if item.value_aud is not None else Decimal("0")
    ownership_rank = item.ownership_pct if item.ownership_pct is not None else Decimal("0")
    return (
        0 if item.value_aud is not None else 1,
        -value_rank,
        0 if item.ownership_pct is not None else 1,
        -ownership_rank,
        item.raw_name.casefold(),
    )


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


def _humanize_disclosure_completeness(value: str) -> str:
    return DISCLOSURE_COMPLETENESS_LABELS.get(value, value.replace("_", " ").title())


def _humanize_observation_kind(value: str) -> str:
    return value.replace("_", " ").title()


def _best_search_candidate(
    *,
    query_casefold: str,
    normalized_query: str,
    candidates: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> tuple[int, str, str] | None:
    best_match: tuple[int, str, str] | None = None
    for matched_on, candidate_value in candidates:
        score = _search_candidate_score(
            query_casefold=query_casefold,
            normalized_query=normalized_query,
            matched_on=matched_on,
            candidate_value=candidate_value,
        )
        if score is None:
            continue
        if best_match is None or score > best_match[0]:
            best_match = (score, matched_on, candidate_value)
    return best_match


def _normalise_search_kind(value: str) -> str:
    normalized_kind = value.strip().casefold()
    if normalized_kind not in SEARCH_FILTER_LABELS:
        raise ValueError(f"Unsupported search kind: {value}")
    return normalized_kind


def _search_candidate_score(
    *,
    query_casefold: str,
    normalized_query: str,
    matched_on: str,
    candidate_value: str,
) -> int | None:
    candidate = candidate_value.strip()
    if candidate == "":
        return None

    candidate_casefold = candidate.casefold()
    candidate_normalized = normalise_name(candidate)
    if candidate_normalized == "":
        return None

    if candidate_normalized == normalized_query:
        strength = 400
    elif candidate_casefold == query_casefold:
        strength = 380
    elif candidate_normalized.startswith(normalized_query):
        strength = 300
    elif candidate_casefold.startswith(query_casefold):
        strength = 280
    elif normalized_query in candidate_normalized:
        strength = 200
    elif query_casefold in candidate_casefold:
        strength = 180
    else:
        return None

    return SEARCH_MATCH_SOURCE_PRIORITY[matched_on] + strength


def _format_homepage_period(period_end_date: date | None) -> str:
    if period_end_date is None:
        return "unavailable"
    return period_end_date.strftime("%d %b %Y")


def _get_homepage_corpus_stats(session: Session) -> dict[str, int]:
    source_file_filters = (
        SourceFile.is_current_version.is_(True),
        SourceFile.ingest_status == "loaded",
    )
    funds_loaded = int(
        session.scalar(
            select(func.count(func.distinct(SourceFile.fund_id))).where(*source_file_filters)
        )
        or 0
    )
    source_files_loaded = int(
        session.scalar(select(func.count(SourceFile.id)).where(*source_file_filters))
        or 0
    )
    holding_rows_loaded = int(
        session.scalar(
            select(func.count(Holding.id))
            .join(SourceFile, SourceFile.id == Holding.source_file_id)
            .where(*source_file_filters)
        )
        or 0
    )

    def reviewed_entity_count(entity_type: str) -> int:
        return int(
            session.scalar(
                select(func.count(func.distinct(Entity.id)))
                .join(Holding, Holding.entity_id == Entity.id)
                .join(SourceFile, SourceFile.id == Holding.source_file_id)
                .where(
                    *source_file_filters,
                    Holding.is_aggregate.is_(False),
                    Entity.entity_type == entity_type,
                    Entity.confidence_tier == "seeded",
                )
            )
            or 0
        )

    return {
        "funds_loaded": funds_loaded,
        "source_files_loaded": source_files_loaded,
        "holding_rows_loaded": holding_rows_loaded,
        "reviewed_companies": reviewed_entity_count("company"),
        "reviewed_managers": reviewed_entity_count("manager"),
    }


def _get_homepage_period_counts(
    session: Session,
    *,
    period_end_date: date | None,
) -> dict[str, int]:
    if period_end_date is None:
        return {
            "fund_count": 0,
            "company_count": 0,
            "manager_count": 0,
        }

    source_file_filters = (
        SourceFile.is_current_version.is_(True),
        SourceFile.ingest_status == "loaded",
        ReportingPeriod.period_end_date == period_end_date,
    )

    fund_count = int(
        session.scalar(
            select(func.count(func.distinct(SourceFile.fund_id)))
            .join(ReportingPeriod, ReportingPeriod.id == SourceFile.reporting_period_id)
            .where(*source_file_filters)
        )
        or 0
    )
    company_count = int(
        session.scalar(
            select(func.count(func.distinct(Holding.entity_id)))
            .join(SourceFile, SourceFile.id == Holding.source_file_id)
            .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
            .join(Entity, Entity.id == Holding.entity_id)
            .where(
                *source_file_filters,
                Holding.is_aggregate.is_(False),
                Entity.entity_type == "company",
            )
        )
        or 0
    )
    manager_count = int(
        session.scalar(
            select(func.count(func.distinct(Holding.entity_id)))
            .join(SourceFile, SourceFile.id == Holding.source_file_id)
            .join(ReportingPeriod, ReportingPeriod.id == Holding.reporting_period_id)
            .join(Entity, Entity.id == Holding.entity_id)
            .where(
                *source_file_filters,
                Holding.is_aggregate.is_(False),
                Entity.entity_type == "manager",
            )
        )
        or 0
    )
    return {
        "fund_count": fund_count,
        "company_count": company_count,
        "manager_count": manager_count,
    }


def _homepage_trend_note(*, current: int, prior: int | None) -> str:
    if prior is None:
        return "No prior loaded period yet"
    delta = current - prior
    if delta > 0:
        return f"Up {delta} vs prior"
    if delta < 0:
        return f"Down {abs(delta)} vs prior"
    return "Flat vs prior"


def _company_entity_confidence(*, confidence_tier: str | None) -> tuple[str, str]:
    normalized_tier = (confidence_tier or "").strip().casefold()
    if normalized_tier == "seeded":
        return (
            "Reviewed",
            "Stored confidence tier is seeded. Current company detail is anchored to a reviewed canonical seed rather than a raw-score display.",
        )
    if normalized_tier == "high":
        return (
            "High Confidence",
            "Stored confidence tier is high confidence. Raw score is intentionally hidden from the default page view.",
        )
    if normalized_tier == "medium":
        return (
            "Medium Confidence",
            "Stored confidence tier is medium confidence. Raw score is intentionally hidden from the default page view.",
        )
    if normalized_tier == "low":
        return (
            "Low Confidence",
            "Stored confidence tier is low confidence. Raw score is intentionally hidden from the default page view.",
        )
    if normalized_tier:
        return (
            confidence_tier.replace("_", " ").title(),
            "Confidence is shown as a tier on the page and not as a raw score by default.",
        )
    return (
        "Linked",
        "No stored confidence tier is present for this canonical entity. Current observations are included because they are linked or match a reviewed alias in current stored truth.",
    )


def _company_observation_confidence(
    *,
    current_entity_id: int,
    observation_entity_id: int | None,
    observation_raw_name: str,
    canonical_name: str,
    normalized_aliases: set[str],
    entity_confidence_label: str,
    entity_confidence_detail: str,
) -> tuple[str, str]:
    if observation_entity_id == current_entity_id:
        return entity_confidence_label, entity_confidence_detail

    normalized_raw_name = normalise_name(observation_raw_name)
    if normalized_raw_name in normalized_aliases and observation_raw_name != canonical_name:
        return (
            "Observed Alias",
            "This row is shown because the observed raw name matches a reviewed alias for the canonical company.",
        )
    if normalized_raw_name in normalized_aliases:
        return (
            "Linked",
            "This row is shown because the observed raw name matches the canonical company record in current stored truth.",
        )
    return (
        "Unresolved",
        "This row is not currently linked strongly enough to receive a cleaner confidence label.",
    )
