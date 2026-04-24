from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import re

from adapters.base import AdapterParseResult, SourceFileMetadata, SourceNormalisedHoldingRecord
from adapters.cbus_errors import (
    CbusFileIdentityError,
    CbusHeaderMismatchError,
    CbusInvalidDateError,
    CbusInvalidNumericError,
    CbusMalformedRowError,
    CbusOutOfRangePercentError,
    CbusUnknownSectionError,
)
from adapters.cbus_mapping import (
    EXPECTED_HEADER,
    INSTITUTION_COLUMN,
    ISSUER_COLUMN,
    MANAGER_NAME_COLUMN,
    PORTFOLIO_NAME_COLUMN,
    SECURITY_NAME_COLUMN,
    lookup_section_mapping,
)


FILE_HEADER_RE = re.compile(
    r"^Portfolio Holdings Information for Investment Option: (?P<option>.+?) - Assets - (?P<date>\d{1,2} [A-Za-z]+ \d{4})$"
)
SECTION_HEADER_RE = re.compile(
    r"^Portfolio Holdings Information for Investment Option: (?P<option>.+?) - (?P<table>Derivatives(?: by Asset Class| by Currency)?)$"
)
TABLE_NUMBERS_BY_LABEL = {
    "Derivatives": 2,
    "Derivatives by Asset Class": 3,
    "Derivatives by Currency": 4,
}
NULL_TOKENS = {"", "-"}
SEDOL_RE = re.compile(r"^[A-Z0-9]{7}$")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class CbusPhdAdapter:
    adapter_key = "CbusPhdAdapter"

    def parse(
        self,
        source_file_metadata: SourceFileMetadata,
        raw_bytes: bytes,
        approved_mapping_config: dict[str, object] | None = None,
    ) -> AdapterParseResult:
        del approved_mapping_config

        text = raw_bytes.decode("utf-8", errors="replace")
        replacement_count = text.count("\ufffd")
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2:
            raise CbusFileIdentityError("Cbus file must include file header and table header rows")
        if any(len(row) != len(EXPECTED_HEADER) for row in rows):
            first_bad = next(index for index, row in enumerate(rows, start=1) if len(row) != len(EXPECTED_HEADER))
            raise CbusMalformedRowError(first_bad, f"expected 14 columns, got {len(rows[first_bad - 1])}")

        option_name, reporting_date = _parse_file_header(_clean_cell(rows[0][0]), row_number=1)
        if [_clean_cell(cell) for cell in rows[1]] != EXPECTED_HEADER:
            raise CbusHeaderMismatchError(f"Expected {EXPECTED_HEADER!r}, received {rows[1]!r}")

        option_code = _slug_option_code(option_name)
        records: list[SourceNormalisedHoldingRecord] = []
        warnings: list[str] = []
        if replacement_count > 0:
            warnings.append(f"UTF-8 replacement characters: {replacement_count}")

        observed_asset_classes: set[str] = set()
        observed_headers = [EXPECTED_HEADER]
        observed_section_labels: set[str] = {"ASSETS"}
        observed_subclasses: set[str] = set()
        observed_tables: set[int] = {1}
        table_rows_skipped_by_table: Counter[str] = Counter()
        rows_emitted_by_asset_class: Counter[str] = Counter()

        current_table = 1
        for row_number, raw_row in enumerate(rows, start=1):
            if row_number <= 2:
                continue
            cleaned_row = [_clean_cell(cell) for cell in raw_row]
            if not any(cleaned_row):
                continue

            table_header = _parse_section_header(cleaned_row[0], option_name=option_name, row_number=row_number)
            if table_header is not None:
                current_table = table_header["table_number"]
                observed_tables.add(current_table)
                observed_section_labels.add(str(table_header["section_label"]))
                continue

            if current_table != 1:
                table_rows_skipped_by_table[str(current_table)] += 1
                continue

            section_label = cleaned_row[0]
            section_mapping = lookup_section_mapping(section_label)
            if section_mapping is None:
                raise CbusUnknownSectionError(row_number, section_label)

            observed_asset_classes.add(section_mapping.source_asset_class_raw)
            if section_mapping.source_subclass_raw is not None:
                observed_subclasses.add(section_mapping.source_subclass_raw)

            value_aud = _parse_decimal(cleaned_row[12], row_number, "Market Value")
            weighting_pct = _parse_percent(cleaned_row[13], row_number, "Weight", allow_negative=True)

            if section_mapping.is_aggregate:
                raw_name = None
                ownership_pct = None
                units = None
                currency_raw = None
                security_identifier_value = None
                security_identifier_type = None
                address_raw = None
                disclosure_completeness = "aggregate_total"
            else:
                ownership_pct = _parse_percent(
                    cleaned_row[8],
                    row_number,
                    "Ownership%",
                    allow_negative=False,
                    enforce_fraction_range=True,
                )
                units = _parse_decimal(cleaned_row[11], row_number, "Units Held")
                currency_raw = _optional_text(cleaned_row[10])
                security_identifier_value = _optional_text(cleaned_row[7])
                security_identifier_type = _infer_identifier_type(security_identifier_value)
                address_raw = _optional_text(cleaned_row[9])
                raw_name = _select_raw_name(
                    cleaned_row=cleaned_row,
                    name_column=section_mapping.name_column,
                    row_number=row_number,
                    section_label=section_label,
                )
                disclosure_completeness = _determine_completeness(
                    value_aud=value_aud,
                    ownership_pct=ownership_pct,
                    units=units,
                    security_identifier_value=security_identifier_value,
                    raw_name=raw_name,
                )

            rows_emitted_by_asset_class[section_mapping.source_asset_class_raw] += 1
            records.append(
                SourceNormalisedHoldingRecord(
                    source_file_id=source_file_metadata.source_file_id,
                    source_fund_id=source_file_metadata.fund_id,
                    source_option_code=option_code,
                    source_option_name_raw=option_name,
                    reporting_period_date=reporting_date,
                    source_asset_class_raw=section_mapping.source_asset_class_raw,
                    source_subclass_raw=section_mapping.source_subclass_raw,
                    canonical_asset_class_code=section_mapping.canonical_asset_class_code,
                    is_aggregate=section_mapping.is_aggregate,
                    raw_name=raw_name,
                    value_aud=value_aud,
                    ownership_pct=ownership_pct,
                    units=units,
                    weighting_pct=weighting_pct,
                    currency_raw=currency_raw,
                    security_identifier_value=security_identifier_value,
                    security_identifier_type=security_identifier_type,
                    address_raw=address_raw,
                    geo_lat=None,
                    geo_lng=None,
                    classification_raw=None,
                    location_raw=None,
                    value_band_raw=None,
                    disclosure_completeness=disclosure_completeness,
                    source_row_number=row_number,
                    source_row_hash=_sha256_of_row(raw_row),
                    raw_payload_json=list(raw_row),
                    parse_warning_flags=[],
                    metadata_attached_from_row_numbers=[],
                )
            )

        asset_class_counts = Counter(record.canonical_asset_class_code for record in records)
        completeness_counts = Counter(record.disclosure_completeness for record in records)
        structural_metadata = {
            "observed_headers": observed_headers,
            "observed_section_labels": sorted(observed_section_labels),
            "observed_tables": sorted(observed_tables),
            "observed_internal_external_values": sorted(observed_subclasses),
            "observed_asset_classes": sorted(observed_asset_classes),
            "observed_options": [option_code],
            "observed_option_names": [option_name],
            "observed_reporting_dates": [reporting_date.isoformat()],
            "total_rows_read": len(rows),
            "total_rows_emitted": len(records),
            "total_rows_aggregate": sum(1 for record in records if record.is_aggregate),
            "table_rows_skipped_by_table": dict(sorted(table_rows_skipped_by_table.items())),
            "rows_emitted_by_asset_class": dict(sorted(rows_emitted_by_asset_class.items())),
            "source_encoding": "utf-8-replace",
            "encoding_replacement_count": replacement_count,
        }
        parse_statistics = {
            **structural_metadata,
            "canonical_asset_class_counts": dict(sorted(asset_class_counts.items())),
            "disclosure_completeness_counts": dict(sorted(completeness_counts.items())),
        }
        schema_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "headers": observed_headers,
                    "section_labels": sorted(observed_section_labels),
                    "asset_classes": sorted(observed_asset_classes),
                    "subclasses": sorted(observed_subclasses),
                    "tables": sorted(observed_tables),
                    "option_names": [option_name],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        return AdapterParseResult(
            holdings=records,
            structural_metadata=structural_metadata,
            adapter_warnings=warnings,
            parse_statistics=parse_statistics,
            schema_fingerprint=schema_fingerprint,
        )


def _clean_cell(value: str) -> str:
    return value.strip()


def _optional_text(value: str) -> str | None:
    cleaned = _clean_cell(value)
    if cleaned in NULL_TOKENS:
        return None
    return cleaned


def _parse_file_header(value: str, *, row_number: int) -> tuple[str, object]:
    match = FILE_HEADER_RE.match(value)
    if not match:
        raise CbusFileIdentityError(f"Unexpected Cbus file header at row {row_number}: {value!r}")
    try:
        reporting_date = datetime.strptime(match.group("date"), "%d %B %Y").date()
    except ValueError as exc:
        raise CbusInvalidDateError(row_number, match.group("date")) from exc
    return match.group("option"), reporting_date


def _parse_section_header(value: str, *, option_name: str, row_number: int) -> dict[str, object] | None:
    match = SECTION_HEADER_RE.match(value)
    if not match:
        return None
    if match.group("option") != option_name:
        raise CbusMalformedRowError(
            row_number,
            f"section header option {match.group('option')!r} did not match file option {option_name!r}",
        )
    section_label = match.group("table")
    return {
        "table_number": TABLE_NUMBERS_BY_LABEL[section_label],
        "section_label": section_label.upper(),
    }


def _parse_decimal(value: str, row_number: int, column_name: str) -> Decimal | None:
    cleaned = _clean_cell(value)
    if cleaned in NULL_TOKENS:
        return None
    normalised = cleaned.replace(",", "").replace(" ", "")
    if normalised.startswith("-$"):
        normalised = "-" + normalised[2:]
    elif normalised.startswith("$"):
        normalised = normalised[1:]
    try:
        return Decimal(normalised)
    except InvalidOperation as exc:
        raise CbusInvalidNumericError(row_number, column_name, cleaned) from exc


def _parse_percent(
    value: str,
    row_number: int,
    column_name: str,
    *,
    allow_negative: bool,
    enforce_fraction_range: bool = False,
) -> Decimal | None:
    cleaned = _clean_cell(value)
    if cleaned in NULL_TOKENS:
        return None
    if not cleaned.endswith("%"):
        raise CbusInvalidNumericError(row_number, column_name, cleaned)
    normalised = cleaned[:-1].replace(",", "").replace(" ", "")
    try:
        result = Decimal(normalised) / Decimal("100")
    except InvalidOperation as exc:
        raise CbusInvalidNumericError(row_number, column_name, cleaned) from exc
    if not allow_negative and result < Decimal("0"):
        raise CbusOutOfRangePercentError(row_number, column_name, cleaned)
    if enforce_fraction_range and (result < Decimal("0") or result > Decimal("1")):
        raise CbusOutOfRangePercentError(row_number, column_name, cleaned)
    return result


def _select_raw_name(
    *,
    cleaned_row: list[str],
    name_column: str | None,
    row_number: int,
    section_label: str,
) -> str:
    column_values = {
        SECURITY_NAME_COLUMN: _optional_text(cleaned_row[2]),
        PORTFOLIO_NAME_COLUMN: _optional_text(cleaned_row[3]),
        MANAGER_NAME_COLUMN: _optional_text(cleaned_row[4]),
        ISSUER_COLUMN: _optional_text(cleaned_row[5]),
        INSTITUTION_COLUMN: _optional_text(cleaned_row[6]),
    }
    if name_column is None:
        raise CbusMalformedRowError(row_number, f"missing name column rule for section {section_label!r}")
    value = column_values.get(name_column)
    if value:
        return value
    raise CbusMalformedRowError(row_number, f"missing {name_column} value for section {section_label!r}")


def _determine_completeness(
    *,
    value_aud: Decimal | None,
    ownership_pct: Decimal | None,
    units: Decimal | None,
    security_identifier_value: str | None,
    raw_name: str | None,
) -> str:
    if value_aud is not None and ownership_pct is not None:
        return "fully_disclosed"
    if value_aud is not None and security_identifier_value:
        return "fully_disclosed"
    if value_aud is not None and units is not None:
        return "fully_disclosed"
    if value_aud is not None:
        return "value_only"
    if ownership_pct is not None:
        return "ownership_only"
    if raw_name:
        return "name_only"
    raise ValueError("Cannot determine disclosure completeness for unnamed Cbus row")


def _infer_identifier_type(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _clean_cell(value)
    if cleaned == "":
        return None
    if ISIN_RE.fullmatch(cleaned):
        return "ISIN"
    if SEDOL_RE.fullmatch(cleaned):
        return "SEDOL"
    return "UNKNOWN"


def _slug_option_code(option_name: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", option_name.upper()).strip("_")
    return f"CBUS_{slug}"


def _sha256_of_row(row: list[str]) -> str:
    payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
