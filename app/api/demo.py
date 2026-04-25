from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.admin import get_db_session
from app.api.admin_ui import SEARCH_KIND_OPTIONS, _render
from app.read_models import get_demo_dashboard, get_demo_entity_explorer


router = APIRouter(tags=["demo-ui"])


@router.get("/demo", response_class=HTMLResponse, name="demo_dashboard")
def demo_dashboard(
    request: Request,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    return _render(
        request,
        "demo_dashboard.html",
        {
            "page_title": "Demo",
            "dashboard": get_demo_dashboard(session),
            "search_kind_options": SEARCH_KIND_OPTIONS,
        },
    )


@router.get("/demo/entities", response_class=HTMLResponse, name="demo_entities")
def demo_entities(
    request: Request,
    sort: str = Query("value_aud_desc"),
    entity_type: str = Query("all", alias="type"),
    disclosure_completeness: list[str] = Query(default=[]),
    fund: list[str] = Query(default=[]),
    canonical_asset_class: list[str] = Query(default=[]),
    page: int = Query(1, ge=1),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    try:
        explorer = get_demo_entity_explorer(
            session,
            entity_type=entity_type,
            disclosure_completeness=disclosure_completeness,
            fund=fund,
            canonical_asset_class=canonical_asset_class,
            sort=sort,
            page=page,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prev_url = None
    next_url = None
    if explorer.page > 1:
        prev_url = str(request.url.include_query_params(page=explorer.page - 1))
    if explorer.page < explorer.total_pages:
        next_url = str(request.url.include_query_params(page=explorer.page + 1))

    return _render(
        request,
        "demo_entities.html",
        {
            "page_title": "Entity Explorer",
            "explorer": explorer,
            "prev_url": prev_url,
            "next_url": next_url,
        },
    )
