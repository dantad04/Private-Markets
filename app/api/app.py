from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from app.api.admin import router as admin_router
from app.api.admin_ui import router as admin_ui_router
from app.api.entities import router as entities_router
from app.api.funds import router as funds_router
from app.api.search import router as search_router


def _format_datetime_utc(value):
    if value is None:
        return ""
    if value.tzinfo is None:
        return f"{value.isoformat()}Z"
    return value.astimezone().isoformat().replace("+00:00", "Z")


def _csv_row(value):
    row = value or []
    if isinstance(row, list) and row and isinstance(row[0], dict):
        rendered_rows = []
        for entry in row:
            source_row_number = entry.get("source_row_number", "?")
            payload = entry.get("payload", [])
            rendered_rows.append(f"row {source_row_number}: {_csv_row(payload)}")
        return "\n".join(rendered_rows)
    if isinstance(row, list) and row and isinstance(row[0], list):
        return "\n".join(_csv_row(item) for item in row)
    if not isinstance(row, list):
        return json.dumps(row, ensure_ascii=False, indent=2)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="")
    writer.writerow(row)
    return buffer.getvalue()


def _json_pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def create_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
    templates.env.filters["iso_utc"] = _format_datetime_utc
    templates.env.filters["csv_row"] = _csv_row
    templates.env.filters["json_pretty"] = _json_pretty
    return templates


def create_app() -> FastAPI:
    app = FastAPI(title="Private Market Insider: Australia - Admin")
    app.state.templates = create_templates()
    app.include_router(admin_router)
    app.include_router(admin_ui_router)
    app.include_router(entities_router)
    app.include_router(funds_router)
    app.include_router(search_router)
    return app


app = create_app()
