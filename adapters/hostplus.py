from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import json
import re

from adapters.base import AdapterParseResult, SourceFileMetadata, SourceNormalisedHoldingRecord
from adapters.hostplus_errors import (
    HostPlusAdapterError,
    HostPlusFileIdentityError,
    HostPlusInvalidNumericError,
    HostPlusMalformedRowError,
    HostPlusUnknownHeaderError,
    HostPlusUnknownSectionError,
)


FUND_MARKER = "HOSTPLUS"
TABLE_RE = re.compile(r"^Table\s+([1-4])\b", re.IGNORECASE)
MANAGEMENT_STYLE_RE = re.compile(r"^(internally|externally)\s+managed$", re.IGNORECASE)
NULL_TOKENS = {"", "N/A", "NAN"}
TABLE_1_ASSET_CLASSES = {
    "Cash": "cash",
    "Fixed Income": "fixed_income",
    "Listed Equity": "listed_equity",
    "Unlisted Alternatives": "alternatives",
    "Unlisted Equity": "unlisted_equity",
    "Unlisted Infrastructure": "unlisted_infrastructure",
    "Unlisted Property": "unlisted_property",
}
SCOPE_VARIANT_TO_CANONICAL = {
    "Held directly or by associated entities or by PSTs": "held_direct_or_associated_or_psts",
}


@dataclass
class ParseState:
    current_option_name: str | None = None
    current_option_code: str | None = None
    current_table: int | None = None
    current_asset_class: str | None = None
    current_scope_modifier: str | None = None
    current_scope_modifier_raw: str | None = None
    current_management_style: str | None = None
    current_header_signature: str | None = None

    def reset_for_table(self, table_number: int) -> None:
        self.current_table = table_number
        self.current_asset_class = None
        self.current_scope_modifier = None
        self.current_scope_modifier_raw = None
        self.current_management_style = None
        self.current_header_signature = None


class HostPlusPhdStateMachineAdapter:
    adapter_key = "HostPlusPhdStateMachineAdapter"

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
        if not rows:
            raise HostPlusFileIdentityError("Host-Plus file was empty")
        if any(len(row) != 5 for row in rows):
            first_bad = next(index for index, row in enumerate(rows, start=1) if len(row) != 5)
            raise HostPlusMalformedRowError(first_bad, "expected exactly 5 columns on every row")

        self._verify_content_signals(rows)

        warnings: list[str] = []
        if replacement_count > 0:
            warnings.append(
                "Decoded Host-Plus source using UTF-8 errors='replace'; replacement_count={count}".format(
                    count=replacement_count
                )
            )

        option_name = _clean_cell(rows[0][0])
        if option_name == "":
            raise HostPlusMalformedRowError(1, "missing option name in first row")
        if source_file_metadata.reporting_period_end_date is None:
            raise HostPlusAdapterError("Host-Plus parsing requires a registered reporting period date")

        state = ParseState(
            current_option_name=option_name,
            current_option_code=_slug_option_code(option_name),
        )
        records: list[SourceNormalisedHoldingRecord] = []
        review_queue_events: list[dict[str, object]] = []
        observed_headers: set[tuple[str, ...]] = set()
        observed_section_labels: set[str] = {"HOSTPLUS"}
        observed_asset_classes: set[str] = set()
        observed_management_styles: set[str] = set()
        observed_investment_statuses: Counter[str] = Counter()
        observed_scope_modifiers: Counter[str] = Counter()
        scope_variant_examples: dict[str, int] = {}
        table_excluded_counts: Counter[int] = Counter()
        rows_emitted_by_option: Counter[str] = Counter()
        rows_emitted_by_option_asset_class: dict[str, Counter[str]] = defaultdict(Counter)
        aggregate_rows_emitted = 0

        for row_number, raw_row in enumerate(rows, start=1):
            cleaned_row = [_clean_cell(cell) for cell in raw_row]
            first_cell = cleaned_row[0]

            if row_number == 1:
                continue

            if not any(cleaned_row):
                continue

            if first_cell == FUND_MARKER:
                observed_section_labels.add("HOSTPLUS")
                continue

            table_match = TABLE_RE.match(first_cell)
            if table_match:
                table_number = int(table_match.group(1))
                state.reset_for_table(table_number)
                observed_section_labels.add(f"TABLE {table_number}")
                continue

            if first_cell.startswith("Portfolio Holdings Information for Investment Option"):
                continue

            if state.current_table == 1 and first_cell in TABLE_1_ASSET_CLASSES:
                state.current_asset_class = first_cell
                state.current_scope_modifier = None
                state.current_scope_modifier_raw = None
                state.current_management_style = None
                state.current_header_signature = None
                observed_asset_classes.add(first_cell)
                observed_section_labels.add(first_cell.upper())
                continue

            if first_cell == "Total Investment Items":
                if state.current_option_name is None or state.current_option_code is None:
                    raise HostPlusMalformedRowError(row_number, "Total Investment Items encountered before option scope")
                record = self._build_holding_record(
                    source_file_metadata=source_file_metadata,
                    state=state,
                    row_number=row_number,
                    raw_row=raw_row,
                    raw_name="TOTAL INVESTMENT ITEMS",
                    source_asset_class_raw="TOTAL INVESTMENT ITEMS",
                    canonical_asset_class_code="multi_asset_other",
                    is_aggregate=True,
                    value_aud=_parse_numeric(cleaned_row[3], row_number, "VALUE (AUD)"),
                    ownership_pct=None,
                    units=None,
                    weighting_pct=_parse_percent(cleaned_row[4], row_number, "WEIGHTING (%)"),
                    currency_raw=None,
                    security_identifier_value=None,
                    security_identifier_type=None,
                    disclosure_completeness="aggregate_total",
                    source_subclass_raw_override=None,
                    classification_raw_override=None,
                )
                records.append(record)
                rows_emitted_by_option[state.current_option_name] += 1
                rows_emitted_by_option_asset_class[state.current_option_name]["TOTAL INVESTMENT ITEMS"] += 1
                aggregate_rows_emitted += 1
                observed_section_labels.add("TOTAL INVESTMENT ITEMS")
                continue

            if _is_investment_status_row(first_cell):
                observed_investment_statuses[first_cell] += 1
                continue

            if first_cell.startswith("Held directly"):
                observed_scope_modifiers[first_cell] += 1
                canonical_scope = SCOPE_VARIANT_TO_CANONICAL.get(first_cell)
                if canonical_scope is None:
                    warnings.append(f"row {row_number}: unapproved scope modifier {first_cell!r}")
                    review_queue_events.append(
                        {
                            "review_reason": "unapproved_scope_modifier",
                            "details": {
                                "row_number": row_number,
                                "scope_modifier_raw": first_cell,
                            },
                        }
                    )
                    canonical_scope = _normalise_scope_fallback(first_cell)
                state.current_scope_modifier = canonical_scope
                state.current_scope_modifier_raw = first_cell
                continue

            management_style_match = MANAGEMENT_STYLE_RE.match(first_cell)
            if management_style_match:
                state.current_management_style = (
                    "Internally Managed" if management_style_match.group(1).casefold() == "internally" else "Externally Managed"
                )
                observed_management_styles.add(state.current_management_style)
                continue

            header_signature = _detect_header_signature(cleaned_row, current_table=state.current_table)
            if header_signature is not None:
                state.current_header_signature = header_signature
                observed_headers.add(tuple(_normalise_header_cell(cell) for cell in cleaned_row))
                continue

            if state.current_table in (2, 3, 4):
                table_excluded_counts[state.current_table] += 1
                continue

            if state.current_table != 1:
                raise HostPlusMalformedRowError(row_number, "data row encountered outside TABLE 1-4 context")
            if first_cell and not any(cleaned_row[1:]):
                raise HostPlusUnknownSectionError(row_number, first_cell)
            if state.current_asset_class is None:
                raise HostPlusUnknownSectionError(row_number, "missing active asset-class section before data row")
            if state.current_header_signature is None:
                raise HostPlusUnknownHeaderError(row_number, cleaned_row)

            if first_cell == "Total":
                record = self._build_total_record(
                    source_file_metadata=source_file_metadata,
                    state=state,
                    row_number=row_number,
                    raw_row=raw_row,
                    cleaned_row=cleaned_row,
                )
                aggregate_rows_emitted += 1
            else:
                record = self._parse_table_1_data_row(
                    source_file_metadata=source_file_metadata,
                    state=state,
                    row_number=row_number,
                    raw_row=raw_row,
                    cleaned_row=cleaned_row,
                )

            if state.current_scope_modifier_raw is not None:
                scope_variant_examples.setdefault(state.current_scope_modifier_raw, record.source_row_number)
            records.append(record)
            rows_emitted_by_option[state.current_option_name or option_name] += 1
            rows_emitted_by_option_asset_class[state.current_option_name or option_name][record.source_asset_class_raw] += 1

        asset_class_counts = Counter(record.canonical_asset_class_code for record in records)
        disclosure_counts = Counter(record.disclosure_completeness for record in records)
        structural_metadata = {
            "observed_headers": [list(header) for header in sorted(observed_headers)],
            "observed_section_labels": sorted(observed_section_labels),
            "observed_tables": [1, 2, 3, 4],
            "observed_internal_external_values": sorted(observed_management_styles),
            "observed_asset_classes": sorted(observed_asset_classes),
            "observed_investment_statuses": dict(sorted(observed_investment_statuses.items())),
            "observed_scope_modifiers": sorted(observed_scope_modifiers.keys()),
            "observed_option_names": [option_name],
            "observed_options": [state.current_option_code or ""],
            "observed_reporting_dates": [source_file_metadata.reporting_period_end_date.isoformat()],
            "options_processed": 1,
            "holdings_rows_emitted": len(records),
            "aggregate_rows_emitted": aggregate_rows_emitted,
            "table_rows_excluded": {str(table): int(table_excluded_counts.get(table, 0)) for table in (2, 3, 4)},
            "rows_emitted_by_option": dict(sorted(rows_emitted_by_option.items())),
            "rows_emitted_by_option_asset_class": {
                option: dict(sorted(counts.items()))
                for option, counts in sorted(rows_emitted_by_option_asset_class.items())
            },
            "scope_modifier_counts": dict(sorted(observed_scope_modifiers.items())),
            "scope_variant_examples": scope_variant_examples,
            "source_encoding": "utf-8-replace",
            "encoding_replacement_count": replacement_count,
            "review_queue_events": review_queue_events,
        }
        parse_statistics = {
            **structural_metadata,
            "canonical_asset_class_counts": dict(sorted(asset_class_counts.items())),
            "disclosure_completeness_counts": dict(sorted(disclosure_counts.items())),
        }
        schema_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "headers": structural_metadata["observed_headers"],
                    "section_labels": structural_metadata["observed_section_labels"],
                    "asset_classes": structural_metadata["observed_asset_classes"],
                    "management_styles": structural_metadata["observed_internal_external_values"],
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

    def _build_total_record(
        self,
        *,
        source_file_metadata: SourceFileMetadata,
        state: ParseState,
        row_number: int,
        raw_row: list[str],
        cleaned_row: list[str],
    ) -> SourceNormalisedHoldingRecord:
        canonical_asset_class = TABLE_1_ASSET_CLASSES.get(state.current_asset_class or "")
        if canonical_asset_class is None:
            raise HostPlusUnknownSectionError(row_number, state.current_asset_class or "")
        return self._build_holding_record(
            source_file_metadata=source_file_metadata,
            state=state,
            row_number=row_number,
            raw_row=raw_row,
            raw_name="TOTAL",
            source_asset_class_raw=state.current_asset_class or "",
            canonical_asset_class_code=canonical_asset_class,
            is_aggregate=True,
            value_aud=_parse_numeric(cleaned_row[3], row_number, "VALUE (AUD)"),
            ownership_pct=None,
            units=None,
            weighting_pct=_parse_percent(cleaned_row[4], row_number, "WEIGHTING (%)"),
            currency_raw=None,
            security_identifier_value=None,
            security_identifier_type=None,
            disclosure_completeness="aggregate_total",
        )

    def _parse_table_1_data_row(
        self,
        *,
        source_file_metadata: SourceFileMetadata,
        state: ParseState,
        row_number: int,
        raw_row: list[str],
        cleaned_row: list[str],
    ) -> SourceNormalisedHoldingRecord:
        canonical_asset_class = TABLE_1_ASSET_CLASSES.get(state.current_asset_class or "")
        if canonical_asset_class is None:
            raise HostPlusUnknownSectionError(row_number, state.current_asset_class or "")

        raw_name = cleaned_row[0] or None
        if raw_name is None:
            raise HostPlusMalformedRowError(row_number, "missing name in TABLE 1 row")

        signature = state.current_header_signature
        value_aud = _parse_numeric(cleaned_row[3], row_number, "VALUE (AUD)")
        weighting_pct = _parse_percent(cleaned_row[4], row_number, "WEIGHTING (%)")
        ownership_pct: Decimal | None = None
        units: Decimal | None = None
        currency_raw: str | None = None
        security_identifier_value: str | None = None
        security_identifier_type: str | None = None
        address_raw: str | None = None

        if signature == "cash":
            currency_raw = cleaned_row[1] or None
        elif signature == "listed_security":
            security_identifier_value = cleaned_row[1] or None
            security_identifier_type = _infer_identifier_type(security_identifier_value)
            units = _parse_numeric(cleaned_row[2], row_number, "UNITS HELD")
        elif signature == "ownership":
            ownership_pct = _parse_percent(cleaned_row[2], row_number, "% OWNERSHIP")
        elif signature == "property_address":
            address_raw = cleaned_row[1] or None
            ownership_pct = _parse_percent(cleaned_row[2], row_number, "% OF PROPERTY HELD")
        elif signature == "manager_value_only":
            pass
        else:
            raise HostPlusUnknownHeaderError(row_number, cleaned_row)

        disclosure_completeness = _determine_disclosure_completeness(
            header_signature=signature,
            value_aud=value_aud,
            ownership_pct=ownership_pct,
        )

        return self._build_holding_record(
            source_file_metadata=source_file_metadata,
            state=state,
            row_number=row_number,
            raw_row=raw_row,
            raw_name=raw_name,
            source_asset_class_raw=state.current_asset_class or "",
            canonical_asset_class_code=canonical_asset_class,
            is_aggregate=False,
            value_aud=value_aud,
            ownership_pct=ownership_pct,
            units=units,
            weighting_pct=weighting_pct,
            currency_raw=currency_raw,
            security_identifier_value=security_identifier_value,
            security_identifier_type=security_identifier_type,
            address_raw=address_raw,
            disclosure_completeness=disclosure_completeness,
        )

    def _build_holding_record(
        self,
        *,
        source_file_metadata: SourceFileMetadata,
        state: ParseState,
        row_number: int,
        raw_row: list[str],
        raw_name: str,
        source_asset_class_raw: str,
        canonical_asset_class_code: str,
        is_aggregate: bool,
        value_aud: Decimal | None,
        ownership_pct: Decimal | None,
        units: Decimal | None,
        weighting_pct: Decimal | None,
        currency_raw: str | None,
        security_identifier_value: str | None,
        security_identifier_type: str | None,
        disclosure_completeness: str,
        address_raw: str | None = None,
        source_subclass_raw_override: str | None | object = ...,
        classification_raw_override: str | None | object = ...,
    ) -> SourceNormalisedHoldingRecord:
        reporting_period_date = source_file_metadata.reporting_period_end_date
        if reporting_period_date is None:
            raise HostPlusAdapterError("Host-Plus parsing requires a registered reporting period date")

        raw_payload_json = [
            {
                "source_row_number": row_number,
                "payload": list(raw_row),
            }
        ]
        source_row_hash = hashlib.sha256(
            json.dumps(raw_payload_json, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        return SourceNormalisedHoldingRecord(
            source_file_id=source_file_metadata.source_file_id,
            source_fund_id=source_file_metadata.fund_id,
            source_option_code=state.current_option_code or "",
            source_option_name_raw=state.current_option_name or "",
            reporting_period_date=reporting_period_date,
            source_asset_class_raw=source_asset_class_raw,
            source_subclass_raw=state.current_management_style
            if source_subclass_raw_override is ...
            else source_subclass_raw_override,
            canonical_asset_class_code=canonical_asset_class_code,
            is_aggregate=is_aggregate,
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
            classification_raw=state.current_scope_modifier if classification_raw_override is ... else classification_raw_override,
            location_raw=None,
            value_band_raw=None,
            disclosure_completeness=disclosure_completeness,
            source_row_number=row_number,
            source_row_hash=source_row_hash,
            raw_payload_json=raw_payload_json,
            parse_warning_flags=[],
            metadata_attached_from_row_numbers=[],
        )

    @staticmethod
    def _verify_content_signals(rows: list[list[str]]) -> None:
        option_name = _clean_cell(rows[0][0])
        if option_name == "" or "Option" not in option_name:
            raise HostPlusFileIdentityError(
                "Host-Plus identity check failed: first row must contain the investment option name"
            )
        if _clean_cell(rows[1][0]) != FUND_MARKER:
            raise HostPlusFileIdentityError("Host-Plus identity check failed: second row must equal 'HOSTPLUS'")

        opening_window = rows[:10]
        if not any(_clean_cell(row[0]).startswith("Table 1 - Assets") for row in opening_window):
            raise HostPlusFileIdentityError(
                "Host-Plus identity check failed: missing 'Table 1 - Assets' marker within the first 10 rows"
            )
        if not any(
            _clean_cell(row[0]).startswith("Portfolio Holdings Information for Investment Option")
            for row in opening_window
        ):
            raise HostPlusFileIdentityError(
                "Host-Plus identity check failed: missing portfolio holdings marker within the first 10 rows"
            )
        if not any(
            _detect_header_signature([_clean_cell(cell) for cell in row], current_table=1) == "cash"
            for row in opening_window
        ):
            raise HostPlusFileIdentityError(
                "Host-Plus identity check failed: missing the cash table header within the first 10 rows"
            )


def _clean_cell(value: str) -> str:
    return value.replace("\xa0", " ").strip()


def _normalise_header_cell(value: str) -> str:
    cleaned = _clean_cell(value).upper()
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.replace(" /", "/").replace("/ ", "/")
    return cleaned


def _detect_header_signature(cells: list[str], *, current_table: int | None) -> str | None:
    normalised = tuple(_normalise_header_cell(cell) for cell in cells)
    first = normalised[0]
    if current_table == 1:
        if first == "NAME OF INSTITUTION" and normalised[1] == "CURRENCY" and normalised[3] == "VALUE (AUD)":
            return "cash"
        if first in {"NAME/KIND OF INVESTMENT ITEM", "NAME /KIND OF INVESTMENT ITEM"} and normalised[1] == "SECURITY IDENTIFIER" and normalised[2] == "UNITS HELD":
            return "listed_security"
        if first in {"NAME/KIND OF INVESTMENT ITEM", "NAME /KIND OF INVESTMENT ITEM"} and normalised[2] == "% OWNERSHIP":
            return "ownership"
        if first in {"NAME/KIND OF INVESTMENT ITEM", "NAME /KIND OF INVESTMENT ITEM"} and normalised[1] == "ADDRESS" and normalised[2] == "% OF PROPERTY HELD":
            return "property_address"
        if first == "NAME OF FUND MANAGER" and normalised[3] == "VALUE (AUD)":
            return "manager_value_only"
    if current_table == 2 and first == "KIND OF DERIVATIVE":
        return "table2"
    if current_table == 3 and first == "ASSET CLASS":
        return "table3"
    if current_table == 4 and first == "CURRENCY EXPOSURE":
        return "table4"
    return None


def _parse_numeric(value: str, row_number: int, column_name: str) -> Decimal | None:
    cleaned = _clean_cell(value)
    if cleaned.upper() in NULL_TOKENS:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    normalised = cleaned.replace(",", "")
    try:
        parsed = Decimal(normalised)
    except InvalidOperation as exc:
        raise HostPlusInvalidNumericError(row_number, column_name, value) from exc
    if negative:
        parsed *= Decimal("-1")
    return parsed


def _parse_percent(value: str, row_number: int, column_name: str) -> Decimal | None:
    cleaned = _clean_cell(value)
    if cleaned.upper() in NULL_TOKENS:
        return None
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1].strip()
    normalised = cleaned.replace(",", "")
    try:
        return Decimal(normalised) / Decimal("100")
    except InvalidOperation as exc:
        raise HostPlusInvalidNumericError(row_number, column_name, value) from exc


def _infer_identifier_type(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _clean_cell(value)
    if cleaned == "":
        return None
    if re.fullmatch(r"[A-Z0-9]{12}", cleaned):
        return "ISIN"
    return "UNKNOWN"


def _slug_option_code(option_name: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", option_name.upper()).strip("_")
    return f"HOSTPLUS_{slug}"


def _is_investment_status_row(value: str) -> bool:
    lowered = value.casefold()
    return lowered.startswith("investment in ") or lowered.startswith("investments in ")


def _normalise_scope_fallback(value: str) -> str:
    lowered = value.casefold()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return lowered


def _determine_disclosure_completeness(
    *,
    header_signature: str,
    value_aud: Decimal | None,
    ownership_pct: Decimal | None,
) -> str:
    if value_aud is not None and ownership_pct is not None:
        if header_signature == "manager_value_only":
            return "value_only"
        return "fully_disclosed"
    if value_aud is not None:
        return "value_only"
    if ownership_pct is not None:
        return "ownership_only"
    return "name_only"
