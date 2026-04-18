from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from adapters.hesta_errors import (
    InvalidDateError,
    InvalidNumericError,
    OutOfRangePercentError,
    UnexpectedNullTokenError,
)


UNEXPECTED_NULL_TOKENS = {"-", "n/a", "nan", "null"}
ISIN_REGEX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def decode_utf8(raw_bytes: bytes) -> tuple[str, int]:
    text = raw_bytes.decode("utf-8", errors="replace")
    return text, text.count("\ufffd")


def clean_cell(value: str) -> str:
    return value.strip()


def assert_not_unexpected_null_token(value: str, row_number: int, column_name: str) -> None:
    stripped = clean_cell(value)
    if stripped and stripped.casefold() in UNEXPECTED_NULL_TOKENS:
        raise UnexpectedNullTokenError(row_number, column_name, stripped)


def parse_uk_date(value: str, row_number: int) -> datetime.date:
    assert_not_unexpected_null_token(value, row_number, "Effective Date")
    stripped = clean_cell(value)
    try:
        return datetime.strptime(stripped, "%d/%m/%Y").date()
    except ValueError as exc:
        raise InvalidDateError(row_number, stripped) from exc


def parse_numeric(value: str, row_number: int, column_name: str) -> Decimal | None:
    assert_not_unexpected_null_token(value, row_number, column_name)
    stripped = clean_cell(value)
    if stripped == "":
        return None
    try:
        return Decimal(stripped)
    except InvalidOperation as exc:
        raise InvalidNumericError(row_number, column_name, stripped) from exc


def parse_percent(value: str, row_number: int, column_name: str) -> Decimal | None:
    assert_not_unexpected_null_token(value, row_number, column_name)
    stripped = clean_cell(value)
    if stripped == "":
        return None
    if not stripped.endswith("%"):
        raise InvalidNumericError(row_number, column_name, stripped)
    numeric_portion = stripped[:-1]
    try:
        result = Decimal(numeric_portion) / Decimal("100")
    except InvalidOperation as exc:
        raise InvalidNumericError(row_number, column_name, stripped) from exc
    if result < Decimal("0") or result > Decimal("1"):
        raise OutOfRangePercentError(row_number, column_name, stripped)
    return result


def infer_identifier_type(value: str) -> str | None:
    stripped = clean_cell(value)
    if stripped == "":
        return None
    if ISIN_REGEX.match(stripped):
        return "ISIN"
    return "UNKNOWN"

