from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from adapters.aware_errors import InvalidDateError, InvalidNumericError, OutOfRangePercentError


NULL_TOKENS = {"", "-"}
ISIN_REGEX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
ASX_CODE_REGEX = re.compile(r"^[A-Z0-9]{2,6}\s+AU$")
SCHEDULE_HEADER_REGEX = re.compile(
    r"^PHD SCHEDULE 8D TABLE (?P<table>[1-4]) - PORTFOLIO HOLDINGS INFORMATION FOR INVESTMENT OPTION "
    r"\[(?P<option>[^\]]+)\] - (?P<section>.+?) - (?P<date>\d{4}-\d{2}-\d{2})$"
)


def decode_utf8(raw_bytes: bytes) -> tuple[str, int]:
    text = raw_bytes.decode("utf-8", errors="replace")
    return text, text.count("\ufffd")


def clean_cell(value: str) -> str:
    return value.strip()


def parse_optional_text(value: str) -> str | None:
    stripped = clean_cell(value)
    if stripped in NULL_TOKENS:
        return None
    return stripped


def parse_iso_date(value: str, row_number: int) -> datetime.date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise InvalidDateError(row_number, value) from exc


def parse_schedule_header(value: str, row_number: int) -> dict[str, object] | None:
    match = SCHEDULE_HEADER_REGEX.match(clean_cell(value))
    if not match:
        return None
    return {
        "table_number": int(match.group("table")),
        "option_code": match.group("option"),
        "section_label": match.group("section"),
        "reporting_period_date": parse_iso_date(match.group("date"), row_number),
    }


def parse_dollar_amount(value: str, row_number: int, column_name: str) -> Decimal | None:
    stripped = clean_cell(value)
    if stripped in NULL_TOKENS:
        return None
    normalised = stripped.replace(",", "")
    if normalised.startswith("-$"):
        normalised = "-" + normalised[2:]
    elif normalised.startswith("$"):
        normalised = normalised[1:]
    else:
        raise InvalidNumericError(row_number, column_name, stripped)
    try:
        return Decimal(normalised)
    except InvalidOperation as exc:
        raise InvalidNumericError(row_number, column_name, stripped) from exc


def parse_numeric(value: str, row_number: int, column_name: str) -> Decimal | None:
    stripped = clean_cell(value)
    if stripped in NULL_TOKENS:
        return None
    normalised = stripped.replace(",", "")
    try:
        return Decimal(normalised)
    except InvalidOperation as exc:
        raise InvalidNumericError(row_number, column_name, stripped) from exc


def parse_percent(
    value: str,
    row_number: int,
    column_name: str,
    *,
    allow_negative: bool = False,
    enforce_fraction_range: bool = False,
) -> Decimal | None:
    stripped = clean_cell(value)
    if stripped in NULL_TOKENS:
        return None
    if not stripped.endswith("%"):
        raise InvalidNumericError(row_number, column_name, stripped)
    normalised = stripped[:-1].replace(",", "")
    if normalised.startswith("+"):
        normalised = normalised[1:]
    try:
        result = Decimal(normalised) / Decimal("100")
    except InvalidOperation as exc:
        raise InvalidNumericError(row_number, column_name, stripped) from exc
    if not allow_negative and result < Decimal("0"):
        raise OutOfRangePercentError(row_number, column_name, stripped)
    if enforce_fraction_range and (result < Decimal("0") or result > Decimal("1")):
        raise OutOfRangePercentError(row_number, column_name, stripped)
    return result


def infer_identifier_type(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = clean_cell(value)
    if stripped in NULL_TOKENS:
        return None
    if ISIN_REGEX.match(stripped):
        return "ISIN"
    if ASX_CODE_REGEX.match(stripped):
        return "ASX_CODE"
    return "UNKNOWN"
