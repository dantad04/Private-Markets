from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from adapters.art_qsuper_errors import ArtQsuperAdapterError
from adapters.aware_errors import AwareAdapterError
from adapters.hostplus_errors import HostPlusAdapterError
from adapters.sunsuper_schema_errors import SunsuperSchemaAdapterError
from adapters.unisuper_errors import UniSuperAdapterError
from app.db.session import get_session
from app.ingest.loader import (
    LoadSummary,
    LoaderError,
    ingest_art_qsuper_local_file,
    ingest_art_sunsuper_local_file,
    ingest_australiansuper_local_file,
    ingest_aware_local_file,
    ingest_hesta_local_file,
    ingest_hostplus_local_file,
    ingest_unisuper_local_file,
)
from app.ingest.governance import SchemaDriftDetectedError, UnapprovedTaxonomyMappingError
from app.read_models import (
    SourceFileDetailReadModel,
    SourceFileHoldingRow,
    SourceFileListItem,
    SourceFileSummary,
    get_source_file_detail,
    list_source_files,
)


router = APIRouter(prefix="/admin", tags=["admin"])


class AdminIngestRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or workspace-local path to the source CSV")
    fund_code: str = Field(..., description="Stable fund code, e.g. 'hesta'")
    fund_name: str = Field(..., description="Human-readable fund name")
    publication_date: date | None = None
    reporting_period_id: int | None = None


class AdminIngestResponse(BaseModel):
    source_file_id: int
    reporting_period_id: int
    investment_option_id: int | None
    rows_staged: int
    rows_inserted: int
    rows_skipped_existing: int
    schema_fingerprint: str
    warnings: list[str]

    @classmethod
    def from_summary(cls, summary: LoadSummary) -> "AdminIngestResponse":
        return cls(**summary.__dict__)


class AdminAwareIngestRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or workspace-local path to the source CSV")
    fund_code: str = Field(..., description="Stable fund code, e.g. 'aware'")
    fund_name: str = Field(..., description="Human-readable fund name")
    publication_date: date | None = None
    reporting_period_id: int | None = None
    terms_snapshot_url: str | None = None
    downloaded_at: datetime | None = None


class AdminArtQsuperIngestRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or workspace-local path to the source CSV")
    fund_code: str = Field(..., description="Stable fund code, e.g. 'art'")
    fund_name: str = Field(..., description="Human-readable fund name")
    publication_date: date | None = None
    reporting_period_id: int | None = None


class AdminArtSunsuperIngestRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or workspace-local path to the source CSV")
    fund_code: str = Field(..., description="Stable fund code, e.g. 'art'")
    fund_name: str = Field(..., description="Human-readable fund name")
    publication_date: date | None = None
    reporting_period_id: int | None = None


class AdminAustralianSuperIngestRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or workspace-local path to the source CSV")
    fund_code: str = Field(..., description="Stable fund code, e.g. 'australiansuper'")
    fund_name: str = Field(..., description="Human-readable fund name")
    publication_date: date | None = None
    reporting_period_id: int | None = None


class AdminUniSuperIngestRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or workspace-local path to the source CSV")
    fund_code: str = Field(..., description="Stable fund code, e.g. 'unisuper'")
    fund_name: str = Field(..., description="Human-readable fund name")
    publication_date: date | None = None
    reporting_period_id: int | None = None


class AdminHostPlusIngestRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or workspace-local path to the source CSV")
    fund_code: str = Field(..., description="Stable fund code, e.g. 'hostplus'")
    fund_name: str = Field(..., description="Human-readable fund name")
    publication_date: date | None = None
    reporting_period_id: int | None = None


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


class SourceFileListItemResponse(BaseModel):
    source_file_id: int
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

    @classmethod
    def from_read_model(cls, item: SourceFileListItem) -> "SourceFileListItemResponse":
        return cls(
            source_file_id=item.id,
            fund_code=item.fund_code,
            fund_name=item.fund_name,
            adapter_key=item.adapter_key,
            schema_fingerprint=item.schema_fingerprint,
            mapping_version_id=item.mapping_version_id,
            ingest_status=item.ingest_status,
            period_end_date=item.period_end_date,
            received_at=item.received_at,
            encoding_replacement_count=item.encoding_replacement_count,
            rows_loaded=item.rows_loaded,
            version_number=item.version_number,
            is_current_version=item.is_current_version,
        )


class SourceFileSummaryResponse(BaseModel):
    source_file_id: int
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

    @classmethod
    def from_read_model(cls, item: SourceFileSummary) -> "SourceFileSummaryResponse":
        return cls(
            source_file_id=item.id,
            fund_id=item.fund_id,
            fund_code=item.fund_code,
            fund_name=item.fund_name,
            investment_option_id=item.investment_option_id,
            investment_option_name=item.investment_option_name,
            adapter_key=item.adapter_key,
            source_url=item.source_url,
            checksum=item.checksum,
            ingest_status=item.ingest_status,
            schema_fingerprint=item.schema_fingerprint,
            mapping_version_id=item.mapping_version_id,
            reporting_period_id=item.reporting_period_id,
            reporting_period_end_date=item.reporting_period_end_date,
            publication_date=item.publication_date,
            terms_snapshot_url=item.terms_snapshot_url,
            downloaded_at=item.downloaded_at,
            received_at=item.received_at,
            encoding_replacement_count=item.encoding_replacement_count,
            version_number=item.version_number,
            is_current_version=item.is_current_version,
            supersedes_source_file_id=item.supersedes_source_file_id,
        )


class SourceFileHoldingRowResponse(BaseModel):
    source_option_code: str
    source_option_name: str
    source_row_number: int
    raw_name: str | None
    source_asset_class_raw: str
    source_subclass_raw: str | None
    canonical_asset_class_code: str
    disclosure_completeness: str
    is_aggregate: bool
    value_aud: str | None
    ownership_pct: str | None
    currency_raw: str | None
    security_identifier_type: str | None
    security_identifier_value: str | None
    value_band_raw: str | None
    raw_payload_json: object
    metadata_attached_from_row_numbers: list[int]
    ingested_at: datetime

    @classmethod
    def from_read_model(cls, item: SourceFileHoldingRow) -> "SourceFileHoldingRowResponse":
        return cls(
            source_option_code=item.source_option_code,
            source_option_name=item.source_option_name,
            source_row_number=item.source_row_number,
            raw_name=item.raw_name,
            source_asset_class_raw=item.source_asset_class_raw,
            source_subclass_raw=item.source_subclass_raw,
            canonical_asset_class_code=item.canonical_asset_class_code,
            disclosure_completeness=item.disclosure_completeness,
            is_aggregate=item.is_aggregate,
            value_aud=_decimal_string(item.value_aud),
            ownership_pct=_decimal_string(item.ownership_pct),
            currency_raw=item.currency_raw,
            security_identifier_type=item.security_identifier_type,
            security_identifier_value=item.security_identifier_value,
            value_band_raw=item.value_band_raw,
            raw_payload_json=item.raw_payload_json,
            metadata_attached_from_row_numbers=item.metadata_attached_from_row_numbers,
            ingested_at=item.ingested_at,
        )


class SourceFileDetailResponse(BaseModel):
    source_file: SourceFileSummaryResponse
    disclosure_counts: dict[str, int]
    canonical_asset_class_counts: dict[str, int]
    holdings: list[SourceFileHoldingRowResponse]
    page: int
    size: int
    total_rows: int
    total_pages: int

    @classmethod
    def from_read_model(cls, detail: SourceFileDetailReadModel) -> "SourceFileDetailResponse":
        return cls(
            source_file=SourceFileSummaryResponse.from_read_model(detail.source_file),
            disclosure_counts=dict(detail.disclosure_counts),
            canonical_asset_class_counts=dict(detail.canonical_asset_class_counts),
            holdings=[SourceFileHoldingRowResponse.from_read_model(row) for row in detail.holdings],
            page=detail.page,
            size=detail.size,
            total_rows=detail.total_rows,
            total_pages=detail.total_pages,
        )


def get_db_session():
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.get("/source-files", response_model=list[SourceFileListItemResponse])
def admin_source_files_list(session: Session = Depends(get_db_session)) -> list[SourceFileListItemResponse]:
    return [SourceFileListItemResponse.from_read_model(item) for item in list_source_files(session)]


@router.get("/source-files/{source_file_id}", response_model=SourceFileDetailResponse)
def admin_source_file_detail(
    source_file_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> SourceFileDetailResponse:
    detail = get_source_file_detail(session, source_file_id=source_file_id, page=page, size=size)
    if detail is None:
        raise HTTPException(status_code=404, detail="Source file not found")
    return SourceFileDetailResponse.from_read_model(detail)


@router.post("/ingest/local-file", response_model=AdminIngestResponse)
def ingest_local_file(payload: AdminIngestRequest, session: Session = Depends(get_db_session)) -> AdminIngestResponse:
    summary = ingest_hesta_local_file(
        session,
        fund_code=payload.fund_code,
        fund_name=payload.fund_name,
        file_path=payload.file_path,
        publication_date=payload.publication_date,
        reporting_period_id=payload.reporting_period_id,
    )
    return AdminIngestResponse.from_summary(summary)


@router.post("/ingest/local-file/aware", response_model=AdminIngestResponse)
def ingest_aware_local_file_endpoint(
    payload: AdminAwareIngestRequest,
    session: Session = Depends(get_db_session),
) -> AdminIngestResponse:
    try:
        summary = ingest_aware_local_file(
            session,
            fund_code=payload.fund_code,
            fund_name=payload.fund_name,
            file_path=payload.file_path,
            publication_date=payload.publication_date,
            reporting_period_id=payload.reporting_period_id,
            terms_snapshot_url=payload.terms_snapshot_url,
            downloaded_at=payload.downloaded_at,
        )
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (AwareAdapterError, LoaderError, OSError, ValueError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminIngestResponse.from_summary(summary)


@router.post("/ingest/local-file/art-qsuper", response_model=AdminIngestResponse)
def ingest_art_qsuper_local_file_endpoint(
    payload: AdminArtQsuperIngestRequest,
    session: Session = Depends(get_db_session),
) -> AdminIngestResponse:
    try:
        summary = ingest_art_qsuper_local_file(
            session,
            fund_code=payload.fund_code,
            fund_name=payload.fund_name,
            file_path=payload.file_path,
            publication_date=payload.publication_date,
            reporting_period_id=payload.reporting_period_id,
        )
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ArtQsuperAdapterError, LoaderError, OSError, ValueError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminIngestResponse.from_summary(summary)


@router.post("/ingest/local-file/art-sunsuper", response_model=AdminIngestResponse)
def ingest_art_sunsuper_local_file_endpoint(
    payload: AdminArtSunsuperIngestRequest,
    session: Session = Depends(get_db_session),
) -> AdminIngestResponse:
    try:
        summary = ingest_art_sunsuper_local_file(
            session,
            fund_code=payload.fund_code,
            fund_name=payload.fund_name,
            file_path=payload.file_path,
            publication_date=payload.publication_date,
            reporting_period_id=payload.reporting_period_id,
        )
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (SunsuperSchemaAdapterError, LoaderError, OSError, ValueError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminIngestResponse.from_summary(summary)


@router.post("/ingest/local-file/australiansuper", response_model=AdminIngestResponse)
def ingest_australiansuper_local_file_endpoint(
    payload: AdminAustralianSuperIngestRequest,
    session: Session = Depends(get_db_session),
) -> AdminIngestResponse:
    try:
        summary = ingest_australiansuper_local_file(
            session,
            fund_code=payload.fund_code,
            fund_name=payload.fund_name,
            file_path=payload.file_path,
            publication_date=payload.publication_date,
            reporting_period_id=payload.reporting_period_id,
        )
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (SunsuperSchemaAdapterError, LoaderError, OSError, ValueError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminIngestResponse.from_summary(summary)


@router.post("/ingest/local-file/unisuper", response_model=AdminIngestResponse)
def ingest_unisuper_local_file_endpoint(
    payload: AdminUniSuperIngestRequest,
    session: Session = Depends(get_db_session),
) -> AdminIngestResponse:
    try:
        summary = ingest_unisuper_local_file(
            session,
            fund_code=payload.fund_code,
            fund_name=payload.fund_name,
            file_path=payload.file_path,
            publication_date=payload.publication_date,
            reporting_period_id=payload.reporting_period_id,
        )
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (UniSuperAdapterError, LoaderError, OSError, ValueError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminIngestResponse.from_summary(summary)


@router.post("/ingest/local-file/hostplus", response_model=AdminIngestResponse)
def ingest_hostplus_local_file_endpoint(
    payload: AdminHostPlusIngestRequest,
    session: Session = Depends(get_db_session),
) -> AdminIngestResponse:
    try:
        summary = ingest_hostplus_local_file(
            session,
            fund_code=payload.fund_code,
            fund_name=payload.fund_name,
            file_path=payload.file_path,
            publication_date=payload.publication_date,
            reporting_period_id=payload.reporting_period_id,
        )
    except (SchemaDriftDetectedError, UnapprovedTaxonomyMappingError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (HostPlusAdapterError, LoaderError, OSError, ValueError) as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminIngestResponse.from_summary(summary)
