from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from app.api.admin import router as admin_router
from app.api.admin_ui import router as admin_ui_router
from app.api.entities import router as entities_router


def _format_datetime_utc(value):
    if value is None:
        return ""
    if value.tzinfo is None:
        return f"{value.isoformat()}Z"
    return value.astimezone().isoformat().replace("+00:00", "Z")


def _csv_row(value):
    row = value or []
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="")
    writer.writerow(row)
    return buffer.getvalue()


def create_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
    templates.env.filters["iso_utc"] = _format_datetime_utc
    templates.env.filters["csv_row"] = _csv_row
    return templates


def create_app() -> FastAPI:
    app = FastAPI(title="Private Market Insider: Australia - Admin")
    app.state.templates = create_templates()
    app.include_router(admin_router)
    app.include_router(admin_ui_router)
    app.include_router(entities_router)
    return app


app = create_app()
