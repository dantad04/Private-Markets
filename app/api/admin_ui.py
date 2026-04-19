from __future__ import annotations

from datetime import date
import math

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.hesta_errors import HestaAdapterError
from app.api.admin import get_db_session
from app.db.models import CanonicalAssetClass, Fund, Holding, ReportingPeriod, SourceFile
from app.ingest.loader import LoaderError, ingest_hesta_local_file


router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])


@router.get("", include_in_schema=False)
def admin_ui_root() -> RedirectResponse:
    return RedirectResponse(url="/admin/ui/source-files", status_code=status.HTTP_303_SEE_OTHER)


def _render(request: Request, template_name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "banner_text": "Stage 1 admin. Internal only. Disclosure completeness shown verbatim — never combine states into totals.",
            **context,
        },
        status_code=status_code,
    )


def _parse_optional_date(value: str) -> date | None:
    if not value.strip():
        return None
    return date.fromisoformat(value)


def _parse_optional_int(value: str) -> int | None:
    if not value.strip():
        return None
    return int(value)


@router.get("/source-files", response_class=HTMLResponse, name="source_files_list")
def source_files_list(
    request: Request,
    flash: str | None = None,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    rows = session.execute(
        select(
            SourceFile.id,
            Fund.code.label("fund_code"),
            SourceFile.adapter_key,
            SourceFile.schema_fingerprint,
            SourceFile.ingest_status,
            ReportingPeriod.period_end_date,
            SourceFile.received_at,
            SourceFile.encoding_replacement_count,
            func.count(Holding.id).label("rows_loaded"),
        )
        .join(Fund, Fund.id == SourceFile.fund_id)
        .outerjoin(ReportingPeriod, ReportingPeriod.id == SourceFile.reporting_period_id)
        .outerjoin(Holding, Holding.source_file_id == SourceFile.id)
        .group_by(
            SourceFile.id,
            Fund.code,
            SourceFile.adapter_key,
            SourceFile.schema_fingerprint,
            SourceFile.ingest_status,
            ReportingPeriod.period_end_date,
            SourceFile.received_at,
            SourceFile.encoding_replacement_count,
        )
        .order_by(SourceFile.received_at.desc(), SourceFile.id.desc())
    ).all()

    return _render(
        request,
        "source_files_list.html",
        {
            "page_title": "Source Files",
            "flash": flash,
            "source_files": rows,
        },
    )


@router.get("/source-files/{source_file_id}", response_class=HTMLResponse, name="source_file_detail")
def source_file_detail(
    request: Request,
    source_file_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    source_file = session.get(SourceFile, source_file_id)
    if source_file is None:
        raise HTTPException(status_code=404, detail="Source file not found")

    fund = session.get(Fund, source_file.fund_id)
    reporting_period = None
    if source_file.reporting_period_id is not None:
        reporting_period = session.get(ReportingPeriod, source_file.reporting_period_id)

    disclosure_counts = session.execute(
        select(Holding.disclosure_completeness, func.count(Holding.id))
        .where(Holding.source_file_id == source_file_id)
        .group_by(Holding.disclosure_completeness)
        .order_by(Holding.disclosure_completeness)
    ).all()

    canonical_asset_class_counts = session.execute(
        select(CanonicalAssetClass.code, func.count(Holding.id))
        .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
        .where(Holding.source_file_id == source_file_id)
        .group_by(CanonicalAssetClass.code)
        .order_by(CanonicalAssetClass.code)
    ).all()

    total_rows = session.scalar(select(func.count(Holding.id)).where(Holding.source_file_id == source_file_id)) or 0
    total_pages = max(1, math.ceil(total_rows / size))
    offset = (page - 1) * size

    holdings = session.execute(
        select(Holding, CanonicalAssetClass.code)
        .join(CanonicalAssetClass, CanonicalAssetClass.id == Holding.canonical_asset_class_id)
        .where(Holding.source_file_id == source_file_id)
        .order_by(Holding.source_row_number.asc(), Holding.id.asc())
        .offset(offset)
        .limit(size)
    ).all()

    prev_url = None
    next_url = None
    if page > 1:
        prev_url = str(request.url.include_query_params(page=page - 1, size=size))
    if page < total_pages:
        next_url = str(request.url.include_query_params(page=page + 1, size=size))

    # Raw payload display is restricted to this internal admin surface for provenance and ingest audit only.
    # Value-band rows are non-precise exposure metadata and must never be folded into displayed totals.
    # Stage 1 shows counts only, so this surface intentionally avoids dollar aggregation entirely.
    return _render(
        request,
        "source_file_detail.html",
        {
            "page_title": f"Source File {source_file_id}",
            "source_file": source_file,
            "fund": fund,
            "reporting_period": reporting_period,
            "disclosure_counts": disclosure_counts,
            "canonical_asset_class_counts": canonical_asset_class_counts,
            "holdings": holdings,
            "page": page,
            "size": size,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "prev_url": prev_url,
            "next_url": next_url,
        },
    )


@router.get("/ingest", response_class=HTMLResponse, name="admin_ui_ingest_form")
def ingest_form(request: Request) -> HTMLResponse:
    return _render(
        request,
        "ingest_form.html",
        {
            "page_title": "Ingest Local File",
            "error_message": None,
            "form_values": {
                "file_path": "",
                "fund_code": "",
                "fund_name": "",
                "publication_date": "",
                "reporting_period_id": "",
            },
        },
    )


@router.post("/ingest", response_class=HTMLResponse, name="admin_ui_ingest_submit")
def ingest_form_submit(
    request: Request,
    file_path: str = Form(...),
    fund_code: str = Form(...),
    fund_name: str = Form(...),
    publication_date: str = Form(""),
    reporting_period_id: str = Form(""),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    form_values = {
        "file_path": file_path,
        "fund_code": fund_code,
        "fund_name": fund_name,
        "publication_date": publication_date,
        "reporting_period_id": reporting_period_id,
    }

    try:
        summary = ingest_hesta_local_file(
            session,
            fund_code=fund_code,
            fund_name=fund_name,
            file_path=file_path,
            publication_date=_parse_optional_date(publication_date),
            reporting_period_id=_parse_optional_int(reporting_period_id),
        )
    except (HestaAdapterError, LoaderError, OSError, ValueError) as exc:
        session.rollback()
        return _render(
            request,
            "ingest_form.html",
            {
                "page_title": "Ingest Local File",
                "error_message": str(exc),
                "form_values": form_values,
            },
            status_code=400,
        )

    flash_message = (
        f"Ingest succeeded. rows_inserted={summary.rows_inserted} "
        f"rows_skipped_existing={summary.rows_skipped_existing} warnings={len(summary.warnings)}"
    )
    redirect_url = str(request.url_for("source_files_list").include_query_params(flash=flash_message))
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
