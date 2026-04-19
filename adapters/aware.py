from __future__ import annotations

import csv
from collections import Counter, defaultdict
import hashlib
import io
import json

from adapters.aware_errors import (
    EmptyFileError,
    HeaderMismatchError,
    InvalidScheduleHeaderError,
    MalformedRowError,
    MultipleDatesError,
    MultipleOptionsError,
    UnknownAssetClassError,
)
from adapters.aware_mapping import (
    EXPECTED_TABLE_1_HEADER,
    parse_aggregate_label,
    lookup_canonical_asset_class,
    select_name_columns,
)
from adapters.aware_normalisation import (
    clean_cell,
    decode_utf8,
    infer_identifier_type,
    parse_dollar_amount,
    parse_numeric,
    parse_optional_text,
    parse_percent,
    parse_schedule_header,
)
from adapters.base import AdapterParseResult, SourceFileMetadata, SourceNormalisedHoldingRecord


class AwarePhdAdapter:
    adapter_key = "AwarePhdAdapter"

    def parse(
        self,
        source_file_metadata: SourceFileMetadata,
        raw_bytes: bytes,
        approved_mapping_config: dict[str, object] | None = None,
    ) -> AdapterParseResult:
        del approved_mapping_config

        text, replacement_count = decode_utf8(raw_bytes)
        warnings: list[str] = []
        if replacement_count > 0:
            warnings.append(f"UTF-8 replacement characters: {replacement_count}")

        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            raise EmptyFileError("Expected at least one schedule header row")

        emitted: list[SourceNormalisedHoldingRecord] = []
        observed_options: set[str] = set()
        observed_dates: set[str] = set()
        observed_section_labels: set[str] = set()
        observed_asset_classes: set[str] = set()
        observed_internal_external_values: set[str] = set()
        observed_tables: set[int] = set()
        skipped_rows_by_table: dict[str, int] = defaultdict(int)

        current_table_number: int | None = None
        current_option_code: str | None = None
        current_reporting_date = None
        table_1_header_seen = False

        for row_number, raw_row in enumerate(rows, start=1):
            raw_payload = list(raw_row)
            cleaned_row = [clean_cell(cell) for cell in raw_payload]
            if not any(cleaned_row):
                continue

            schedule_header = parse_schedule_header(cleaned_row[0], row_number)
            if schedule_header is not None:
                current_table_number = int(schedule_header["table_number"])
                current_option_code = str(schedule_header["option_code"])
                current_reporting_date = schedule_header["reporting_period_date"]
                observed_tables.add(current_table_number)
                observed_options.add(current_option_code)
                observed_dates.add(current_reporting_date.isoformat())
                observed_section_labels.add(str(schedule_header["section_label"]))
                continue

            if current_table_number is None:
                raise InvalidScheduleHeaderError(row_number, cleaned_row[0])
            if current_option_code is None or current_reporting_date is None:
                raise MalformedRowError(row_number, "missing active option/date state")

            if current_table_number != 1:
                skipped_rows_by_table[str(current_table_number)] += 1
                continue

            if cleaned_row != EXPECTED_TABLE_1_HEADER:
                if not table_1_header_seen and cleaned_row[0] == "ASSET CLASS":
                    raise HeaderMismatchError(
                        f"Expected {EXPECTED_TABLE_1_HEADER!r}, received {cleaned_row!r}"
                    )
            if cleaned_row == EXPECTED_TABLE_1_HEADER:
                table_1_header_seen = True
                continue

            if not table_1_header_seen:
                raise HeaderMismatchError("Expected Table 1 header row before holdings rows")

            if len(cleaned_row) != len(EXPECTED_TABLE_1_HEADER):
                raise MalformedRowError(row_number, f"expected 14 columns, got {len(cleaned_row)}")

            (
                asset_class_raw,
                internal_external_raw,
                institution_raw,
                issuer_raw,
                fund_manager_raw,
                name_kind_raw,
                currency_raw,
                security_identifier_raw,
                address_raw,
                ownership_raw,
                units_raw,
                value_raw,
                weighting_raw,
                _blank,
            ) = raw_payload

            source_asset_class_raw = clean_cell(asset_class_raw)
            if source_asset_class_raw == "":
                raise MalformedRowError(row_number, "missing asset class")

            aggregate_info = parse_aggregate_label(source_asset_class_raw)
            if aggregate_info is not None:
                base_asset_class = aggregate_info.base_asset_class
                source_subclass = aggregate_info.source_subclass_raw
                is_aggregate = True
            else:
                base_asset_class = source_asset_class_raw
                source_subclass = parse_optional_text(internal_external_raw)
                is_aggregate = False

            canonical_asset_class_code = lookup_canonical_asset_class(base_asset_class)
            if canonical_asset_class_code is None:
                raise UnknownAssetClassError(row_number, source_asset_class_raw)

            observed_asset_classes.add(base_asset_class)
            if source_subclass is not None:
                observed_internal_external_values.add(source_subclass)

            value_aud = parse_dollar_amount(value_raw, row_number, "VALUE(AUD)")
            weighting_pct = parse_percent(
                weighting_raw,
                row_number,
                "WEIGHTING(%)",
                allow_negative=True,
                enforce_fraction_range=False,
            )

            if is_aggregate:
                raw_name = None
                ownership_pct = None
                units = None
                currency = None
                security_identifier_value = None
                security_identifier_type = None
                address = None
                disclosure_completeness = "aggregate_total"
            else:
                ownership_pct = parse_percent(
                    ownership_raw,
                    row_number,
                    "% OWNERSHIP / PROPERTY HELD",
                    allow_negative=False,
                    enforce_fraction_range=True,
                )
                units = parse_numeric(units_raw, row_number, "UNITS HELD")
                currency = parse_optional_text(currency_raw)
                security_identifier_value = parse_optional_text(security_identifier_raw)
                security_identifier_type = infer_identifier_type(security_identifier_value)
                address = parse_optional_text(address_raw)
                raw_name = self._select_raw_name(
                    base_asset_class=base_asset_class,
                    source_subclass=source_subclass,
                    institution_raw=institution_raw,
                    issuer_raw=issuer_raw,
                    fund_manager_raw=fund_manager_raw,
                    name_kind_raw=name_kind_raw,
                    row_number=row_number,
                )
                disclosure_completeness = self._determine_completeness(
                    value_aud=value_aud,
                    ownership_pct=ownership_pct,
                    units=units,
                    security_identifier_value=security_identifier_value,
                    raw_name=raw_name,
                )

            emitted.append(
                SourceNormalisedHoldingRecord(
                    source_file_id=source_file_metadata.source_file_id,
                    source_fund_id=source_file_metadata.fund_id,
                    source_option_code=current_option_code,
                    source_option_name_raw=current_option_code,
                    reporting_period_date=current_reporting_date,
                    source_asset_class_raw=source_asset_class_raw,
                    source_subclass_raw=source_subclass,
                    canonical_asset_class_code=canonical_asset_class_code,
                    is_aggregate=is_aggregate,
                    raw_name=raw_name,
                    value_aud=value_aud,
                    ownership_pct=ownership_pct,
                    units=units,
                    weighting_pct=weighting_pct,
                    currency_raw=currency,
                    security_identifier_value=security_identifier_value,
                    security_identifier_type=security_identifier_type,
                    address_raw=address,
                    geo_lat=None,
                    geo_lng=None,
                    classification_raw=None,
                    location_raw=None,
                    value_band_raw=None,
                    disclosure_completeness=disclosure_completeness,
                    source_row_number=row_number,
                    source_row_hash=self._sha256_of_row(raw_payload),
                    raw_payload_json=raw_payload,
                    parse_warning_flags=[],
                    metadata_attached_from_row_numbers=[],
                )
            )

        if len(observed_options) != 1:
            raise MultipleOptionsError(sorted(observed_options))
        if len(observed_dates) != 1:
            raise MultipleDatesError(sorted(observed_dates))
        if not table_1_header_seen:
            raise HeaderMismatchError("Expected Aware Table 1 header row")

        asset_class_counts = Counter(record.canonical_asset_class_code for record in emitted)
        completeness_counts = Counter(record.disclosure_completeness for record in emitted)

        structural_metadata = {
            "observed_headers": EXPECTED_TABLE_1_HEADER,
            "observed_asset_classes": sorted(observed_asset_classes),
            "observed_options": sorted(observed_options),
            "observed_reporting_dates": sorted(observed_dates),
            "observed_section_labels": sorted(observed_section_labels),
            "observed_internal_external_values": sorted(observed_internal_external_values),
            "observed_tables": sorted(observed_tables),
            "total_rows_read": len(rows),
            "total_rows_emitted": len(emitted),
            "total_rows_aggregate": sum(1 for record in emitted if record.is_aggregate),
            "encoding_replacement_count": replacement_count,
            "table_rows_skipped_by_table": dict(sorted(skipped_rows_by_table.items())),
        }
        parse_statistics = {
            **structural_metadata,
            "canonical_asset_class_counts": dict(sorted(asset_class_counts.items())),
            "disclosure_completeness_counts": dict(sorted(completeness_counts.items())),
        }

        schema_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "table_1_header": EXPECTED_TABLE_1_HEADER,
                    "observed_asset_classes": sorted(observed_asset_classes),
                    "observed_internal_external_values": sorted(observed_internal_external_values),
                    "observed_section_labels": sorted(observed_section_labels),
                    "observed_tables": sorted(observed_tables),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        return AdapterParseResult(
            holdings=emitted,
            structural_metadata=structural_metadata,
            adapter_warnings=warnings,
            parse_statistics=parse_statistics,
            schema_fingerprint=schema_fingerprint,
        )

    @staticmethod
    def _select_raw_name(
        *,
        base_asset_class: str,
        source_subclass: str | None,
        institution_raw: str,
        issuer_raw: str,
        fund_manager_raw: str,
        name_kind_raw: str,
        row_number: int,
    ) -> str:
        candidates = {
            "institution": parse_optional_text(institution_raw),
            "issuer_counterparty": parse_optional_text(issuer_raw),
            "fund_manager": parse_optional_text(fund_manager_raw),
            "name_kind": parse_optional_text(name_kind_raw),
        }
        for column_name in select_name_columns(base_asset_class, source_subclass):
            value = candidates.get(column_name)
            if value:
                return value
        raise MalformedRowError(
            row_number,
            f"unable to select raw name for {base_asset_class!r} / {source_subclass!r}",
        )

    @staticmethod
    def _determine_completeness(
        *,
        value_aud,
        ownership_pct,
        units,
        security_identifier_value,
        raw_name,
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
        raise ValueError("Cannot determine disclosure completeness for unnamed empty row")

    @staticmethod
    def _sha256_of_row(row: list[str]) -> str:
        payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
