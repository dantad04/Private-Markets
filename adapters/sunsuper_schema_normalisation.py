from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

from adapters.sunsuper_schema_errors import InvalidNumericError


NULL_TOKENS = {"", "n/a", "nan"}
ISIN_REGEX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
ASX_CODE_REGEX = re.compile(r"^[A-Z0-9]{2,6}\s+AU$")


def decode_utf8(raw_bytes: bytes) -> tuple[str, int]:
    text = raw_bytes.decode("utf-8", errors="replace")
    return text, text.count("\ufffd")


def clean_cell(value: str) -> str:
    return value.strip()


def parse_optional_text(value: str) -> str | None:
    stripped = clean_cell(value)
    if stripped.casefold() in NULL_TOKENS:
        return None
    return stripped


def parse_numeric(value: str, row_number: int, column_name: str) -> Decimal | None:
    stripped = clean_cell(value)
    if stripped.casefold() in NULL_TOKENS:
        return None
    normalised = stripped.replace(",", "")
    try:
        return Decimal(normalised)
    except InvalidOperation as exc:
        raise InvalidNumericError(row_number, column_name, stripped) from exc


def parse_bare_percent_decimal(value: str, row_number: int, column_name: str) -> Decimal | None:
    # The Sunsuper schema already stores ownership as a decimal fraction.
    # Example: 0.18 means 18%, so canonical storage stays 0.18.
    return parse_numeric(value, row_number, column_name)


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


def normalise_name(value: str) -> str:
    return " ".join(clean_cell(value).casefold().split())
