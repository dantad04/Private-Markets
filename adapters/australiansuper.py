from __future__ import annotations

import csv
from decimal import Decimal
import io

from adapters.australiansuper_mapping import PORTFOLIO_POSTURE_ASSET_CLASSES, derive_row_shape
from adapters.australiansuper_normalisation import (
    clean_cell,
    decode_utf8,
    infer_identifier_type,
    parse_numeric,
    parse_optional_text,
    parse_percentage_points,
    parse_signed_percentage_points,
)
from adapters.base import AdapterParseResult, SourceFileMetadata, SourceNormalisedHoldingRecord
from adapters.sunsuper_schema import ParsedSourceRow, SunsuperSchemaPhdAdapter
from adapters.sunsuper_schema_errors import EmptyFileError, HeaderMismatchError, MalformedRowError, MultipleOptionsError
from adapters.sunsuper_schema_identity import AUSTRALIANSUPER_REAL_HEADER


class AustralianSuperPhdAdapter(SunsuperSchemaPhdAdapter):
    adapter_key = "AustralianSuperPhdAdapter"

    def parse(
        self,
        source_file_metadata: SourceFileMetadata,
        raw_bytes: bytes,
        approved_mapping_config: dict[str, object] | None = None,
    ) -> AdapterParseResult:
        del approved_mapping_config

        if source_file_metadata.reporting_period_end_date is None:
            raise MalformedRowError(0, "AustralianSuper files require reporting period date from file registration")

        text, replacement_count = decode_utf8(raw_bytes)
        warnings: list[str] = []
        if replacement_count > 0:
            warnings.append(f"UTF-8 replacement characters: {replacement_count}")

        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2:
            raise EmptyFileError("Expected header plus at least one data row")

        header = [clean_cell(cell) for cell in rows[0]]
        if header != AUSTRALIANSUPER_REAL_HEADER:
            raise HeaderMismatchError(f"Expected {AUSTRALIANSUPER_REAL_HEADER!r}, received {header!r}")

        parsed_rows: list[ParsedSourceRow] = []
        aggregate_records: list[SourceNormalisedHoldingRecord] = []
        observed_option_codes: set[str] = set()
        observed_option_names: set[str] = set()
        observed_filters: set[str] = set()
        observed_name_types: set[str] = set()
        observed_asset_classes: set[str] = set()
        observed_input_filters: set[str] = set()
        observed_input_sub_filters: set[str] = set()
        observed_input_asset_classes: set[str] = set()
        skipped_portfolio_posture_rows = 0

        for row_number, raw_row in enumerate(rows[1:], start=2):
            raw_payload = list(raw_row)
            cleaned_row = [clean_cell(cell) for cell in raw_payload]
            if not any(cleaned_row):
                continue
            if len(cleaned_row) != len(AUSTRALIANSUPER_REAL_HEADER):
                raise MalformedRowError(row_number, f"expected 24 columns, got {len(cleaned_row)}")

            (
                option_code_raw,
                option_name_raw,
                asset_class_raw,
                filter_raw,
                sub_filter_raw,
                name_raw,
                name_type_raw,
                currency_raw,
                _issuer_type_raw,
                security_identifier_raw,
                units_raw,
                location_raw,
                address_raw,
                ownership_raw,
                value_raw,
                weighting_raw,
                _actual_currency_exposure_raw,
                _actual_asset_allocation_raw,
                _derivatives_exposure_raw,
                classification_raw,
                _sort_order_raw,
                value_range_raw,
                geo_lat_raw,
                geo_lng_raw,
            ) = raw_payload

            option_code = clean_cell(option_code_raw)
            option_name = clean_cell(option_name_raw)
            raw_asset_class = clean_cell(asset_class_raw)
            raw_filter = clean_cell(filter_raw)
            raw_sub_filter = clean_cell(sub_filter_raw)
            name_type_value = clean_cell(name_type_raw)
            raw_name = clean_cell(name_raw)

            if option_code == "":
                raise MalformedRowError(row_number, "missing Option Code")
            if option_name == "":
                raise MalformedRowError(row_number, "missing Option Name")
            if raw_asset_class == "":
                raise MalformedRowError(row_number, "missing Asset Class")
            if name_type_value == "":
                raise MalformedRowError(row_number, "missing Name Type")
            if name_type_value != "Total" and raw_name == "":
                raise MalformedRowError(row_number, "missing Name")

            observed_option_codes.add(option_code)
            observed_option_names.add(option_name)
            observed_name_types.add(name_type_value)
            observed_input_asset_classes.add(raw_asset_class)
            observed_input_filters.add(raw_filter)
            observed_input_sub_filters.add(raw_sub_filter)

            if raw_asset_class.casefold() in PORTFOLIO_POSTURE_ASSET_CLASSES:
                skipped_portfolio_posture_rows += 1
                continue

            derived_shape = derive_row_shape(
                row_number=row_number,
                asset_class_raw=raw_asset_class,
                filter_raw=raw_filter,
                sub_filter_raw=raw_sub_filter,
            )
            observed_asset_classes.add(derived_shape.normalised_asset_class_raw)
            observed_filters.add(derived_shape.qualifier)

            parsed_row = ParsedSourceRow(
                row_number=row_number,
                raw_payload=raw_payload,
                option_code=option_code,
                option_name=option_name,
                filter_raw=derived_shape.qualifier,
                asset_class_raw=derived_shape.normalised_asset_class_raw,
                name_type_raw=name_type_value,
                raw_name=raw_name or "Total",
                canonical_asset_class_code=derived_shape.canonical_asset_class_code,
                security_identifier_value=parse_optional_text(security_identifier_raw),
                security_identifier_type=infer_identifier_type(parse_optional_text(security_identifier_raw)),
                currency_raw=parse_optional_text(currency_raw),
                units=parse_numeric(units_raw, row_number, "Units Held"),
                value_aud=parse_numeric(value_raw, row_number, "$ Value"),
                ownership_pct=parse_percentage_points(ownership_raw, row_number, "% Ownership"),
                weighting_pct=parse_signed_percentage_points(weighting_raw, row_number, "Weighting (%)"),
                value_band_raw=parse_optional_text(value_range_raw),
                classification_raw=parse_optional_text(classification_raw),
                address_raw=parse_optional_text(address_raw),
                location_raw=parse_optional_text(location_raw),
                geo_lat=parse_numeric(geo_lat_raw, row_number, "Geo Latitude"),
                geo_lng=parse_numeric(geo_lng_raw, row_number, "Geo Longitude"),
                current_management_style_raw=derived_shape.current_management_style_raw,
            )

            if name_type_value == "Total":
                aggregate_records.append(
                    self._build_aggregate_record(
                        source_file_metadata=source_file_metadata,
                        row=parsed_row,
                    )
                )
                continue

            parsed_rows.append(parsed_row)

        if len(observed_option_codes) != 1:
            raise MultipleOptionsError(sorted(observed_option_codes))

        result = self._finalise_parse_result(
            source_file_metadata=source_file_metadata,
            header=header,
            parsed_rows=parsed_rows,
            aggregate_records=aggregate_records,
            observed_option_codes=observed_option_codes,
            observed_option_names=observed_option_names,
            observed_filters=observed_filters,
            observed_name_types=observed_name_types,
            observed_asset_classes=observed_asset_classes,
            replacement_count=replacement_count,
            skipped_portfolio_posture_rows=skipped_portfolio_posture_rows,
            total_rows_read=len(rows),
            warnings=warnings,
        )
        result.structural_metadata["observed_input_asset_classes"] = sorted(value for value in observed_input_asset_classes if value)
        result.structural_metadata["observed_input_filters"] = sorted(value for value in observed_input_filters if value)
        result.structural_metadata["observed_input_sub_filters"] = sorted(
            value for value in observed_input_sub_filters if value
        )
        result.parse_statistics["observed_input_asset_classes"] = result.structural_metadata["observed_input_asset_classes"]
        result.parse_statistics["observed_input_filters"] = result.structural_metadata["observed_input_filters"]
        result.parse_statistics["observed_input_sub_filters"] = result.structural_metadata["observed_input_sub_filters"]
        return result

    def _build_aggregate_record(
        self,
        *,
        source_file_metadata: SourceFileMetadata,
        row: ParsedSourceRow,
    ) -> SourceNormalisedHoldingRecord:
        raw_payload_entries = [self._raw_payload_entry(row)]
        return SourceNormalisedHoldingRecord(
            source_file_id=source_file_metadata.source_file_id,
            source_fund_id=source_file_metadata.fund_id,
            source_option_code=row.option_code,
            source_option_name_raw=row.option_name,
            reporting_period_date=source_file_metadata.reporting_period_end_date,
            source_asset_class_raw=row.asset_class_raw,
            source_subclass_raw=row.filter_raw,
            canonical_asset_class_code=row.canonical_asset_class_code,
            is_aggregate=True,
            raw_name=None,
            value_aud=row.value_aud,
            ownership_pct=None,
            units=row.units,
            weighting_pct=row.weighting_pct,
            currency_raw=row.currency_raw,
            security_identifier_value=None,
            security_identifier_type=None,
            address_raw=None,
            geo_lat=None,
            geo_lng=None,
            classification_raw=None,
            location_raw=None,
            value_band_raw=None,
            disclosure_completeness="aggregate_total",
            source_row_number=row.row_number,
            source_row_hash=self._sha256_of_payload(raw_payload_entries),
            raw_payload_json=raw_payload_entries,
            parse_warning_flags=[],
            metadata_attached_from_row_numbers=[],
        )
