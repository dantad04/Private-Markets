from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from adapters.australian_retirement_trust_real_16col_errors import (
    InvalidDateError,
    InvalidNumericError,
)


NULL_TOKENS = {"", "n/a"}
ISIN_REGEX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
ASX_CODE_REGEX = re.compile(r"^[A-Z0-9]{2,6}\s+AU$")


def decode_utf8(raw_bytes: bytes) -> tuple[str, int]:
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    return text, text.count("\ufffd")


def clean_cell(value: str) -> str:
    return value.strip()


def parse_optional_text(value: str) -> str | None:
    stripped = clean_cell(value)
    if stripped.casefold() in NULL_TOKENS:
        return None
    return stripped


def parse_textual_date(value: str, row_number: int):
    stripped = clean_cell(value)
    if stripped.casefold() in NULL_TOKENS:
        raise InvalidDateError(row_number, stripped)
    try:
        return datetime.strptime(stripped, "%d %B %Y").date()
    except ValueError as exc:
        raise InvalidDateError(row_number, stripped) from exc


def parse_dollar_amount(value: str, row_number: int, column_name: str) -> Decimal | None:
    stripped = clean_cell(value)
    if stripped.casefold() in NULL_TOKENS:
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
    if stripped.casefold() in NULL_TOKENS:
        return None
    normalised = stripped.replace(",", "")
    try:
        return Decimal(normalised)
    except InvalidOperation as exc:
        raise InvalidNumericError(row_number, column_name, stripped) from exc


def parse_percent(value: str, row_number: int, column_name: str) -> Decimal | None:
    stripped = clean_cell(value)
    if stripped.casefold() in NULL_TOKENS:
        return None
    if not stripped.endswith("%"):
        raise InvalidNumericError(row_number, column_name, stripped)
    normalised = stripped[:-1].replace(",", "")
    try:
        return Decimal(normalised) / Decimal("100")
    except InvalidOperation as exc:
        raise InvalidNumericError(row_number, column_name, stripped) from exc


def infer_identifier_type(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = clean_cell(value)
    if stripped.casefold() in NULL_TOKENS:
        return None
    if ISIN_REGEX.match(stripped):
        return "ISIN"
    if ASX_CODE_REGEX.match(stripped):
        return "ASX_CODE"
    return "UNKNOWN"
