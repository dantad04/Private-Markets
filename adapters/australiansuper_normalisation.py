from __future__ import annotations

from decimal import Decimal

from adapters.sunsuper_schema_errors import InvalidNumericError
from adapters.sunsuper_schema_normalisation import (
    clean_cell,
    decode_utf8,
    infer_identifier_type,
    normalise_name,
    parse_numeric,
    parse_optional_text,
)


def parse_percentage_points(value: str, row_number: int, column_name: str) -> Decimal | None:
    parsed = parse_numeric(value, row_number, column_name)
    if parsed is None:
        return None
    scaled = parsed / Decimal("100")
    if scaled < Decimal("0") or scaled > Decimal("1"):
        raise InvalidNumericError(row_number, column_name, clean_cell(value))
    return scaled


def parse_signed_percentage_points(value: str, row_number: int, column_name: str) -> Decimal | None:
    parsed = parse_numeric(value, row_number, column_name)
    if parsed is None:
        return None
    scaled = parsed / Decimal("100")
    if scaled < Decimal("-1") or scaled > Decimal("1"):
        raise InvalidNumericError(row_number, column_name, clean_cell(value))
    return scaled
