from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from adapters.hesta_errors import HestaAdapterError
from app.api.admin import get_db_session
from app.ingest.loader import LoaderError, ingest_hesta_local_file
from app.read_models import get_source_file_detail, list_source_files


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
    return _render(
        request,
        "source_files_list.html",
        {
            "page_title": "Source Files",
            "flash": flash,
            "source_files": list_source_files(session),
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
    detail = get_source_file_detail(session, source_file_id=source_file_id, page=page, size=size)
    if detail is None:
        raise HTTPException(status_code=404, detail="Source file not found")

    prev_url = None
    next_url = None
    if detail.page > 1:
        prev_url = str(request.url.include_query_params(page=page - 1, size=size))
    if detail.page < detail.total_pages:
        next_url = str(request.url.include_query_params(page=page + 1, size=size))

    # Raw payload display is restricted to this internal admin surface for provenance and ingest audit only.
    # Value-band rows are non-precise exposure metadata and must never be folded into displayed totals.
    # Stage 1 shows counts only, so this surface intentionally avoids dollar aggregation entirely.
    return _render(
        request,
        "source_file_detail.html",
        {
            "page_title": f"Source File {source_file_id}",
            "source_file": detail.source_file,
            "disclosure_counts": detail.disclosure_counts,
            "canonical_asset_class_counts": detail.canonical_asset_class_counts,
            "holdings": detail.holdings,
            "page": detail.page,
            "size": detail.size,
            "total_rows": detail.total_rows,
            "total_pages": detail.total_pages,
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
