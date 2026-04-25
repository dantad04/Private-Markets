from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import io
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from app.api.admin import router as admin_router
from app.api.admin_ui import router as admin_ui_router
from app.api.demo import router as demo_router
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


def _coerce_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_raw(value) -> str:
    decimal_value = _coerce_decimal(value)
    if decimal_value is None:
        return str(value)
    if decimal_value == 0:
        return "0"
    rendered = format(decimal_value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _compact_scaled_number(value: Decimal, divisor: Decimal, decimal_places: int) -> str:
    quantizer = Decimal("1") if decimal_places == 0 else Decimal("1").scaleb(-decimal_places)
    rendered = format((value / divisor).quantize(quantizer), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _format_aud_compact(value) -> str:
    decimal_value = _coerce_decimal(value)
    if decimal_value is None:
        return "—"
    if decimal_value == 0:
        return "$0"

    absolute_value = abs(decimal_value)
    sign = "-" if decimal_value < 0 else ""
    if absolute_value >= Decimal("1000000000"):
        return f"{sign}${_compact_scaled_number(absolute_value, Decimal('1000000000'), 2)}b"
    if absolute_value >= Decimal("1000000"):
        return f"{sign}${_compact_scaled_number(absolute_value, Decimal('1000000'), 1)}m"
    if absolute_value >= Decimal("1000"):
        return f"{sign}${_compact_scaled_number(absolute_value, Decimal('1000'), 1)}k"
    return f"{sign}${_compact_scaled_number(absolute_value, Decimal('1'), 0)}"


def _format_pct_compact(value) -> str:
    decimal_value = _coerce_decimal(value)
    if decimal_value is None:
        return "—"
    if decimal_value > Decimal("1") or decimal_value < Decimal("-1"):
        return _decimal_raw(decimal_value)
    return f"{(decimal_value * Decimal('100')).quantize(Decimal('0.01'))}%"


_DISCLOSURE_LABELS = {
    "fully_disclosed": "Direct",
    "value_only": "Value only",
    "ownership_only": "Ownership only",
    "name_only": "Name only",
    "aggregate_total": "Section total",
}


def _format_disclosure_label(value) -> str:
    if value is None:
        return ""
    raw_value = str(value)
    return _DISCLOSURE_LABELS.get(raw_value, raw_value.replace("_", " ").title())


def create_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
    templates.env.filters["iso_utc"] = _format_datetime_utc
    templates.env.filters["csv_row"] = _csv_row
    templates.env.filters["json_pretty"] = _json_pretty
    templates.env.filters["aud_compact"] = _format_aud_compact
    templates.env.filters["pct_compact"] = _format_pct_compact
    templates.env.filters["disclosure_label"] = _format_disclosure_label
    return templates


def create_app() -> FastAPI:
    app = FastAPI(title="Private Market Insider: Australia - Admin")
    app.state.templates = create_templates()
    app.include_router(admin_router)
    app.include_router(admin_ui_router)
    app.include_router(demo_router)
    app.include_router(entities_router)
    app.include_router(funds_router)
    app.include_router(search_router)
    return app


app = create_app()
