from __future__ import annotations

from datetime import date
import json
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from adapters.hesta_errors import HestaAdapterError
from app.api.admin import get_db_session
from app.entity_resolution.queue import apply_entity_resolution_queue_action
from app.ingest.loader import LoaderError, ingest_hesta_local_file
from app.read_models import (
    SEARCH_FILTER_LABELS,
    approve_schema_review_mapping,
    get_company_detail,
    get_cross_adapter_holdings_by_name,
    get_entity_resolution_queue_detail,
    get_fund_detail,
    get_australiansuper_stable_matched_asset_proof,
    get_homepage,
    get_manager_detail,
    get_schema_review_queue_detail,
    get_source_file_detail,
    list_entity_resolution_queue_items,
    list_schema_review_queue_items,
    list_source_files,
    search_entities_and_funds,
    update_schema_review_queue_status,
)


router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])

SEARCH_KIND_OPTIONS = [
    {"value": search_kind, "label": label}
    for search_kind, label in SEARCH_FILTER_LABELS.items()
]


@router.get("", include_in_schema=False)
def admin_ui_root(
    request: Request,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    return _render(
        request,
        "home.html",
        {
            "page_title": "Home",
            "homepage": get_homepage(session),
            "search_kind_options": SEARCH_KIND_OPTIONS,
        },
    )


def _render(request: Request, template_name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "banner_text": (
                "Internal admin. Disclosure completeness shown verbatim — never combine states into totals. "
                "Schema-review items require human approval before mapping changes are trusted."
            ),
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


@router.get("/cross-adapter", response_class=HTMLResponse, name="cross_adapter_lookup")
def cross_adapter_lookup(
    request: Request,
    name: str = Query(""),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    lookup_name = name.strip()
    detail = None
    if lookup_name:
        detail = get_cross_adapter_holdings_by_name(session, name=lookup_name)

    return _render(
        request,
        "cross_adapter_lookup.html",
        {
            "page_title": "Cross-Adapter Lookup",
            "lookup_name": lookup_name,
            "detail": detail,
            "lookup_performed": bool(lookup_name),
        },
    )


@router.get("/search", response_class=HTMLResponse, name="search_page")
def search_page(
    request: Request,
    q: str = Query(""),
    result_type: Literal["all", "company", "fund", "manager"] = Query("all", alias="type"),
    kind: Literal["all", "company", "fund", "manager"] | None = Query(None, include_in_schema=False),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    lookup_query = q.strip()
    active_kind = result_type if result_type != "all" or kind is None else kind
    search = None
    if lookup_query:
        search = search_entities_and_funds(session, query=lookup_query, kind=active_kind)

    return _render(
        request,
        "search.html",
        {
            "page_title": "Search",
            "query": lookup_query,
            "active_kind": active_kind,
            "search": search,
            "search_kind_options": SEARCH_KIND_OPTIONS,
            "lookup_performed": bool(lookup_query),
        },
    )


@router.get("/managers/{entity_id}", response_class=HTMLResponse, name="manager_detail_page")
def manager_detail_page(
    request: Request,
    entity_id: int,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    detail = get_manager_detail(session, entity_id=entity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Manager detail not found")

    return _render(
        request,
        "manager_detail.html",
        {
            "page_title": f"Manager Detail {entity_id}",
            "detail": detail,
        },
    )


@router.get("/companies/{entity_id}", response_class=HTMLResponse, name="company_detail_page")
def company_detail_page(
    request: Request,
    entity_id: int,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    detail = get_company_detail(session, entity_id=entity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Company detail not found")

    return _render(
        request,
        "company_detail.html",
        {
            "page_title": f"Company Detail {entity_id}",
            "detail": detail,
        },
    )


@router.get("/funds/{fund_code}", response_class=HTMLResponse, name="fund_detail_page")
def fund_detail_page(
    request: Request,
    fund_code: str,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    detail = get_fund_detail(session, fund_code=fund_code)
    if detail is None:
        raise HTTPException(status_code=404, detail="Fund detail not found")

    return _render(
        request,
        "fund_detail.html",
        {
            "page_title": f"Fund Detail {detail.fund_code}",
            "detail": detail,
        },
    )


@router.get(
    "/matched-assets/australiansuper-stable-stage5-proof",
    response_class=HTMLResponse,
    name="australiansuper_stable_matched_asset_proof_page",
)
def australiansuper_stable_matched_asset_proof_page(
    request: Request,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    return _render(
        request,
        "matched_asset_proof.html",
        {
            "page_title": "AustralianSuper Stable Matched-Asset Proof",
            "detail": get_australiansuper_stable_matched_asset_proof(session),
        },
    )


@router.get("/entity-resolution-queue", response_class=HTMLResponse, name="entity_resolution_queue_list")
def entity_resolution_queue_list(
    request: Request,
    flash: str | None = None,
    queue_status: str = Query("open", alias="status"),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    return _render(
        request,
        "entity_resolution_queue_list.html",
        {
            "page_title": "Entity Resolution Queue",
            "flash": flash,
            "queue_status": queue_status,
            "queue_items": list_entity_resolution_queue_items(session, status_filter=queue_status),
        },
    )


@router.get("/entity-resolution-queue/{queue_item_id}", response_class=HTMLResponse, name="entity_resolution_queue_detail")
def entity_resolution_queue_detail(
    request: Request,
    queue_item_id: int,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    detail = get_entity_resolution_queue_detail(session, queue_item_id=queue_item_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Entity resolution item not found")

    return _render(
        request,
        "entity_resolution_queue_detail.html",
        {
            "page_title": f"Entity Resolution Item {queue_item_id}",
            "detail": detail,
        },
    )


@router.post("/entity-resolution-queue/{queue_item_id}/action", name="entity_resolution_queue_action")
def entity_resolution_queue_action(
    request: Request,
    queue_item_id: int,
    action: str = Form(...),
    entity_id: str = Form(""),
    resolved_by: str = Form("admin-ui"),
    notes: str = Form(""),
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    chosen_entity_id = int(entity_id) if entity_id.strip() else None
    try:
        queue_item = apply_entity_resolution_queue_action(
            session,
            queue_item_id=queue_item_id,
            action=action,
            chosen_entity_id=chosen_entity_id,
            resolved_by=resolved_by or "admin-ui",
            notes=notes or None,
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400 if "already" not in str(exc) else 409, detail=str(exc)) from exc
    if queue_item is None:
        raise HTTPException(status_code=404, detail="Entity resolution item not found")

    flash_message = f"Entity resolution item {queue_item_id} marked {queue_item.status}."
    redirect_url = str(
        request.url_for("entity_resolution_queue_list").include_query_params(flash=flash_message, status="open")
    )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/schema-review-queue", response_class=HTMLResponse, name="schema_review_queue_list")
def schema_review_queue_list(
    request: Request,
    flash: str | None = None,
    queue_status: str = Query("open", alias="status"),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    return _render(
        request,
        "schema_review_queue_list.html",
        {
            "page_title": "Schema Review Queue",
            "flash": flash,
            "queue_status": queue_status,
            "review_items": list_schema_review_queue_items(session, status_filter=queue_status),
        },
    )


@router.get("/schema-review-queue/{review_item_id}", response_class=HTMLResponse, name="schema_review_queue_detail")
def schema_review_queue_detail(
    request: Request,
    review_item_id: int,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    detail = get_schema_review_queue_detail(session, review_item_id=review_item_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Schema review item not found")

    return _render(
        request,
        "schema_review_queue_detail.html",
        {
            "page_title": f"Schema Review Item {review_item_id}",
            "review_item": detail.review_item,
            "source_file": detail.source_file,
            "approved_mapping_version": detail.approved_mapping_version,
            "drift_summary_json": detail.drift_summary_json,
            "sample_rows_json": detail.sample_rows_json,
        },
    )


@router.post("/schema-review-queue/{review_item_id}/status", name="schema_review_queue_update_status")
def schema_review_queue_update_status(
    request: Request,
    review_item_id: int,
    new_status: str = Form(..., alias="status"),
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    try:
        detail = update_schema_review_queue_status(session, review_item_id=review_item_id, new_status=new_status)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400 if "already" not in str(exc) else 409, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Schema review item not found")

    flash_message = f"Review item {review_item_id} marked {detail.review_item.status}."
    redirect_url = str(request.url_for("schema_review_queue_list").include_query_params(flash=flash_message, status="open"))
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/schema-review-queue/{review_item_id}/approve-mapping", name="schema_review_queue_approve_mapping")
def schema_review_queue_approve_mapping(
    request: Request,
    review_item_id: int,
    mapping_version_id: str = Form(...),
    approved_by: str = Form(...),
    notes: str = Form(""),
    structural_expectations_json: str = Form(...),
    taxonomy_mappings_json: str = Form(...),
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    try:
        parsed_structural_expectations = json.loads(structural_expectations_json)
    except json.JSONDecodeError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail="structural_expectations_json must be valid JSON") from exc
    try:
        parsed_taxonomy_mappings = json.loads(taxonomy_mappings_json)
    except json.JSONDecodeError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail="taxonomy_mappings_json must be valid JSON") from exc

    if not isinstance(parsed_structural_expectations, dict):
        raise HTTPException(status_code=400, detail="structural_expectations_json must decode to a JSON object")
    if not isinstance(parsed_taxonomy_mappings, list):
        raise HTTPException(status_code=400, detail="taxonomy_mappings_json must decode to a JSON array")

    try:
        detail = approve_schema_review_mapping(
            session,
            review_item_id=review_item_id,
            mapping_version_id=mapping_version_id,
            approved_by=approved_by,
            notes=notes,
            structural_expectations_json=parsed_structural_expectations,
            taxonomy_mappings_payload=parsed_taxonomy_mappings,
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400 if "already" not in str(exc) else 409, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Schema review item not found")

    flash_message = (
        f"Review item {review_item_id} approved as mapping {detail.review_item.approved_mapping_version_id}."
    )
    redirect_url = str(request.url_for("schema_review_queue_list").include_query_params(flash=flash_message, status="open"))
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


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
