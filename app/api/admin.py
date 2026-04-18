from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.ingest.loader import LoadSummary, ingest_hesta_local_file


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
    investment_option_id: int
    rows_staged: int
    rows_inserted: int
    rows_skipped_existing: int
    schema_fingerprint: str
    warnings: list[str]

    @classmethod
    def from_summary(cls, summary: LoadSummary) -> "AdminIngestResponse":
        return cls(**summary.__dict__)


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

