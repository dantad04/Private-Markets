from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.admin import get_db_session
from app.read_models import SearchResultReadModel, SearchResultsReadModel, search_entities_and_funds


router = APIRouter(prefix="/search", tags=["search"])


class SearchResultResponse(BaseModel):
    result_kind: str
    result_kind_label: str
    title: str
    matched_on: str
    matched_on_label: str
    matched_value: str
    entity_id: int | None
    fund_code: str | None

    @classmethod
    def from_read_model(cls, item: SearchResultReadModel) -> "SearchResultResponse":
        return cls(
            result_kind=item.result_kind,
            result_kind_label=item.result_kind_label,
            title=item.title,
            matched_on=item.matched_on,
            matched_on_label=item.matched_on_label,
            matched_value=item.matched_value,
            entity_id=item.entity_id,
            fund_code=item.fund_code,
        )


class SearchResponse(BaseModel):
    query: str
    normalized_query: str
    active_kind: str
    result_count: int
    total_result_count: int
    kind_counts: dict[str, int]
    results: list[SearchResultResponse]

    @classmethod
    def from_read_model(cls, item: SearchResultsReadModel) -> "SearchResponse":
        return cls(
            query=item.query,
            normalized_query=item.normalized_query,
            active_kind=item.active_kind,
            result_count=item.result_count,
            total_result_count=item.total_result_count,
            kind_counts=item.kind_counts,
            results=[SearchResultResponse.from_read_model(row) for row in item.results],
        )


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, description="Search query across funds, companies, managers, and aliases"),
    result_type: Literal["all", "company", "fund", "manager"] = Query(
        "all",
        alias="type",
        description="Optional result-scope filter for the existing search surfaces.",
    ),
    kind: Literal["all", "company", "fund", "manager"] | None = Query(None, include_in_schema=False),
    limit: int = Query(20, ge=1, le=50),
    session: Session = Depends(get_db_session),
) -> SearchResponse:
    active_kind = result_type if result_type != "all" or kind is None else kind
    return SearchResponse.from_read_model(search_entities_and_funds(session, query=q, kind=active_kind, limit=limit))
