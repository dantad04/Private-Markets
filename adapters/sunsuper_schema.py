from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import io
import json

from adapters.base import AdapterParseResult, SourceFileMetadata, SourceNormalisedHoldingRecord
from adapters.sunsuper_schema_errors import (
    EmptyFileError,
    HeaderMismatchError,
    MalformedRowError,
    MultipleOptionsError,
    UnknownAssetClassError,
)
from adapters.sunsuper_schema_mapping import (
    EXPECTED_HEADER,
    MANAGEMENT_STYLE_FILTERS,
    METADATA_ATTACHING_FILTERS,
    PORTFOLIO_POSTURE_FILTERS,
    lookup_asset_class_mapping,
    lookup_option_family_owner,
)
from adapters.sunsuper_schema_normalisation import (
    clean_cell,
    decode_utf8,
    infer_identifier_type,
    normalise_name,
    parse_bare_percent_decimal,
    parse_numeric,
    parse_optional_text,
)


@dataclass(frozen=True)
class ParsedSourceRow:
    row_number: int
    raw_payload: list[str]
    option_code: str
    option_name: str
    filter_raw: str
    asset_class_raw: str
    name_type_raw: str
    raw_name: str
    canonical_asset_class_code: str
    security_identifier_value: str | None
    security_identifier_type: str | None
    currency_raw: str | None
    units: Decimal | None
    value_aud: Decimal | None
    ownership_pct: Decimal | None
    weighting_pct: Decimal | None
    value_band_raw: str | None
    classification_raw: str | None
    address_raw: str | None
    location_raw: str | None
    geo_lat: Decimal | None
    geo_lng: Decimal | None
    current_management_style_raw: str | None


class SunsuperSchemaPhdAdapter:
    adapter_key = "SunsuperSchemaPhdAdapter"

    def parse(
        self,
        source_file_metadata: SourceFileMetadata,
        raw_bytes: bytes,
        approved_mapping_config: dict[str, object] | None = None,
    ) -> AdapterParseResult:
        del approved_mapping_config

        if source_file_metadata.reporting_period_end_date is None:
            raise MalformedRowError(0, "Sunsuper schema requires reporting period date from file registration")

        text, replacement_count = decode_utf8(raw_bytes)
        warnings: list[str] = []
        if replacement_count > 0:
            warnings.append(f"UTF-8 replacement characters: {replacement_count}")

        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2:
            raise EmptyFileError("Expected header plus at least one data row")

        header = [clean_cell(cell) for cell in rows[0]]
        if header != EXPECTED_HEADER:
            raise HeaderMismatchError(f"Expected {EXPECTED_HEADER!r}, received {header!r}")

        parsed_rows: list[ParsedSourceRow] = []
        observed_option_codes: set[str] = set()
        observed_option_names: set[str] = set()
        observed_filters: set[str] = set()
        observed_name_types: set[str] = set()
        observed_asset_classes: set[str] = set()
        skipped_portfolio_posture_rows = 0

        for row_number, raw_row in enumerate(rows[1:], start=2):
            raw_payload = list(raw_row)
            cleaned_row = [clean_cell(cell) for cell in raw_payload]
            if not any(cleaned_row):
                continue
            if len(cleaned_row) != len(EXPECTED_HEADER):
                raise MalformedRowError(row_number, f"expected 24 columns, got {len(cleaned_row)}")

            (
                option_code_raw,
                option_name_raw,
                filter_raw,
                asset_class_raw,
                name_type_raw,
                name_raw,
                security_identifier_raw,
                currency_raw,
                units_raw,
                value_raw,
                ownership_raw,
                weighting_raw,
                value_range_raw,
                classification_raw,
                address_raw,
                location_raw,
                geo_lat_raw,
                geo_lng_raw,
                current_management_style_raw,
                _issuer_name_raw,
                _manager_name_raw,
                _country_raw,
                _notes_raw,
                _source_view_raw,
            ) = raw_payload

            option_code = clean_cell(option_code_raw)
            option_name = clean_cell(option_name_raw)
            filter_value = clean_cell(filter_raw)
            asset_class_value = clean_cell(asset_class_raw)
            name_type_value = clean_cell(name_type_raw)
            raw_name = clean_cell(name_raw)

            if option_code == "":
                raise MalformedRowError(row_number, "missing OptionCode")
            if option_name == "":
                raise MalformedRowError(row_number, "missing OptionName")
            if filter_value == "":
                raise MalformedRowError(row_number, "missing Filter")
            if asset_class_value == "":
                raise MalformedRowError(row_number, "missing AssetClass")
            if name_type_value == "":
                raise MalformedRowError(row_number, "missing NameType")
            if raw_name == "":
                raise MalformedRowError(row_number, "missing Name")

            observed_option_codes.add(option_code)
            observed_option_names.add(option_name)
            observed_filters.add(filter_value)
            observed_name_types.add(name_type_value)
            observed_asset_classes.add(asset_class_value)

            if filter_value.casefold() in PORTFOLIO_POSTURE_FILTERS:
                skipped_portfolio_posture_rows += 1
                continue

            mapping = lookup_asset_class_mapping(asset_class_value)
            if mapping is None:
                raise UnknownAssetClassError(row_number, asset_class_value, filter_value)

            parsed_rows.append(
                ParsedSourceRow(
                    row_number=row_number,
                    raw_payload=raw_payload,
                    option_code=option_code,
                    option_name=option_name,
                    filter_raw=filter_value,
                    asset_class_raw=asset_class_value,
                    name_type_raw=name_type_value,
                    raw_name=raw_name,
                    canonical_asset_class_code=mapping.canonical_code,
                    security_identifier_value=parse_optional_text(security_identifier_raw),
                    security_identifier_type=infer_identifier_type(parse_optional_text(security_identifier_raw)),
                    currency_raw=parse_optional_text(currency_raw),
                    units=parse_numeric(units_raw, row_number, "UnitsHeld"),
                    value_aud=parse_numeric(value_raw, row_number, "MarketValueAud"),
                    ownership_pct=parse_bare_percent_decimal(ownership_raw, row_number, "OwnershipPct"),
                    weighting_pct=parse_numeric(weighting_raw, row_number, "WeightingPct"),
                    value_band_raw=parse_optional_text(value_range_raw),
                    classification_raw=parse_optional_text(classification_raw),
                    address_raw=parse_optional_text(address_raw),
                    location_raw=parse_optional_text(location_raw),
                    geo_lat=parse_numeric(geo_lat_raw, row_number, "GeoLat"),
                    geo_lng=parse_numeric(geo_lng_raw, row_number, "GeoLng"),
                    current_management_style_raw=parse_optional_text(current_management_style_raw),
                )
            )

        if len(observed_option_codes) != 1:
            raise MultipleOptionsError(sorted(observed_option_codes))

        option_code = next(iter(observed_option_codes))
        option_family_owner = lookup_option_family_owner(option_code)
        if option_family_owner is None:
            warnings.append(f"Unknown option-code family for {option_code!r}")

        merged_records, ambiguous_review_events = self._merge_duplicate_views(
            source_file_metadata=source_file_metadata,
            parsed_rows=parsed_rows,
        )
        if ambiguous_review_events:
            warnings.append(
                f"Ambiguous duplicate groups emitted separately: {len(ambiguous_review_events)}"
            )

        asset_class_counts = Counter(record.canonical_asset_class_code for record in merged_records)
        completeness_counts = Counter(record.disclosure_completeness for record in merged_records)

        structural_metadata = {
            "observed_headers": header,
            "observed_asset_classes": sorted(observed_asset_classes),
            "observed_option_codes": sorted(observed_option_codes),
            "observed_option_names": sorted(observed_option_names),
            "observed_options": sorted(observed_option_codes),
            "observed_reporting_dates": [source_file_metadata.reporting_period_end_date.isoformat()],
            "observed_filters": sorted(observed_filters),
            "observed_name_types": sorted(observed_name_types),
            "known_option_family_owner": option_family_owner,
            "total_rows_read": len(rows),
            "total_rows_emitted": len(merged_records),
            "total_rows_aggregate": 0,
            "encoding_replacement_count": replacement_count,
            "skipped_portfolio_posture_rows": skipped_portfolio_posture_rows,
            "merged_duplicate_groups": sum(
                1 for record in merged_records if record.metadata_attached_from_row_numbers
            ),
            "ambiguous_duplicate_groups": ambiguous_review_events,
            "review_queue_events": [
                {
                    "review_reason": "ambiguous_duplicate_group",
                    "details": event,
                }
                for event in ambiguous_review_events
            ],
        }
        parse_statistics = {
            **structural_metadata,
            "canonical_asset_class_counts": dict(sorted(asset_class_counts.items())),
            "disclosure_completeness_counts": dict(sorted(completeness_counts.items())),
        }

        schema_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "header": header,
                    "asset_classes": sorted(observed_asset_classes),
                    "filters": sorted(observed_filters),
                    "name_types": sorted(observed_name_types),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        return AdapterParseResult(
            holdings=merged_records,
            structural_metadata=structural_metadata,
            adapter_warnings=warnings,
            parse_statistics=parse_statistics,
            schema_fingerprint=schema_fingerprint,
        )

    def _merge_duplicate_views(
        self,
        *,
        source_file_metadata: SourceFileMetadata,
        parsed_rows: list[ParsedSourceRow],
    ) -> tuple[list[SourceNormalisedHoldingRecord], list[dict[str, object]]]:
        groups: dict[tuple[str, str, str], list[ParsedSourceRow]] = defaultdict(list)
        for row in parsed_rows:
            groups[(row.option_code, row.asset_class_raw, normalise_name(row.raw_name))].append(row)

        emitted: list[SourceNormalisedHoldingRecord] = []
        ambiguous_review_events: list[dict[str, object]] = []

        for (_option_code, _asset_class_raw, _normalised_name), group_rows in sorted(
            groups.items(),
            key=lambda item: min(row.row_number for row in item[1]),
        ):
            management_value_rows = [
                row for row in group_rows if self._is_precise_management_row(row)
            ]
            metadata_rows = [
                row
                for row in group_rows
                if row.filter_raw.casefold() in METADATA_ATTACHING_FILTERS and row.value_aud is None
            ]

            if len(management_value_rows) == 1 and metadata_rows:
                emitted.append(
                    self._build_merged_record(
                        source_file_metadata=source_file_metadata,
                        precise_row=management_value_rows[0],
                        metadata_rows=metadata_rows,
                    )
                )
                remaining = [row for row in group_rows if row not in metadata_rows and row not in management_value_rows]
                for row in remaining:
                    emitted.append(self._build_single_record(source_file_metadata=source_file_metadata, row=row))
                continue

            if len(management_value_rows) > 1:
                ambiguous_review_events.append(
                    {
                        "group_key": {
                            "option_code": group_rows[0].option_code,
                            "asset_class": group_rows[0].asset_class_raw,
                            "raw_name": group_rows[0].raw_name,
                        },
                        "reason": "multiple_precise_rows_within_group",
                        "source_row_numbers": sorted(row.row_number for row in group_rows),
                    }
                )

            for row in group_rows:
                emitted.append(self._build_single_record(source_file_metadata=source_file_metadata, row=row))

        cross_asset_rows: dict[tuple[str, str], list[ParsedSourceRow]] = defaultdict(list)
        for row in parsed_rows:
            if row.value_aud is None:
                continue
            cross_asset_rows[(row.option_code, normalise_name(row.raw_name))].append(row)

        for (option_code, _name_key), rows in sorted(cross_asset_rows.items()):
            asset_classes = {row.asset_class_raw for row in rows}
            if len(asset_classes) <= 1:
                continue
            ambiguous_review_events.append(
                {
                    "group_key": {
                        "option_code": option_code,
                        "raw_name": rows[0].raw_name,
                    },
                    "reason": "same_name_value_rows_across_asset_classes",
                    "asset_classes": sorted(asset_classes),
                    "source_row_numbers": sorted(row.row_number for row in rows),
                }
            )

        return emitted, ambiguous_review_events

    @staticmethod
    def _is_precise_management_row(row: ParsedSourceRow) -> bool:
        return row.value_aud is not None and row.filter_raw.casefold() in MANAGEMENT_STYLE_FILTERS

    def _build_merged_record(
        self,
        *,
        source_file_metadata: SourceFileMetadata,
        precise_row: ParsedSourceRow,
        metadata_rows: list[ParsedSourceRow],
    ) -> SourceNormalisedHoldingRecord:
        merged_payloads = [
            self._raw_payload_entry(precise_row),
            *[self._raw_payload_entry(row) for row in metadata_rows],
        ]
        attached_row_numbers = [row.row_number for row in metadata_rows]
        classification = precise_row.classification_raw or self._first_non_null(metadata_rows, "classification_raw")
        address = precise_row.address_raw or self._first_non_null(metadata_rows, "address_raw")
        location = precise_row.location_raw or self._first_non_null(metadata_rows, "location_raw")
        value_band = precise_row.value_band_raw or self._first_non_null(metadata_rows, "value_band_raw")
        geo_lat = precise_row.geo_lat if precise_row.geo_lat is not None else self._first_non_null(metadata_rows, "geo_lat")
        geo_lng = precise_row.geo_lng if precise_row.geo_lng is not None else self._first_non_null(metadata_rows, "geo_lng")
        parse_warning_flags = ["metadata_attached"]

        return SourceNormalisedHoldingRecord(
            source_file_id=source_file_metadata.source_file_id,
            source_fund_id=source_file_metadata.fund_id,
            source_option_code=precise_row.option_code,
            source_option_name_raw=precise_row.option_name,
            reporting_period_date=source_file_metadata.reporting_period_end_date,
            source_asset_class_raw=precise_row.asset_class_raw,
            source_subclass_raw=precise_row.filter_raw,
            canonical_asset_class_code=precise_row.canonical_asset_class_code,
            is_aggregate=False,
            raw_name=precise_row.raw_name,
            value_aud=precise_row.value_aud,
            ownership_pct=precise_row.ownership_pct,
            units=precise_row.units,
            weighting_pct=precise_row.weighting_pct,
            currency_raw=precise_row.currency_raw,
            security_identifier_value=precise_row.security_identifier_value,
            security_identifier_type=precise_row.security_identifier_type,
            address_raw=address,
            geo_lat=geo_lat,
            geo_lng=geo_lng,
            classification_raw=classification,
            location_raw=location,
            value_band_raw=value_band,
            disclosure_completeness=self._determine_completeness(precise_row, management_style_row=True),
            source_row_number=precise_row.row_number,
            source_row_hash=self._sha256_of_payload(merged_payloads),
            raw_payload_json=merged_payloads,
            parse_warning_flags=parse_warning_flags,
            metadata_attached_from_row_numbers=attached_row_numbers,
        )

    def _build_single_record(
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
            is_aggregate=False,
            raw_name=row.raw_name,
            value_aud=row.value_aud,
            ownership_pct=row.ownership_pct,
            units=row.units,
            weighting_pct=row.weighting_pct,
            currency_raw=row.currency_raw,
            security_identifier_value=row.security_identifier_value,
            security_identifier_type=row.security_identifier_type,
            address_raw=row.address_raw,
            geo_lat=row.geo_lat,
            geo_lng=row.geo_lng,
            classification_raw=row.classification_raw,
            location_raw=row.location_raw,
            value_band_raw=row.value_band_raw,
            disclosure_completeness=self._determine_completeness(
                row,
                management_style_row=row.filter_raw.casefold() in MANAGEMENT_STYLE_FILTERS,
            ),
            source_row_number=row.row_number,
            source_row_hash=self._sha256_of_payload(raw_payload_entries),
            raw_payload_json=raw_payload_entries,
            parse_warning_flags=[],
            metadata_attached_from_row_numbers=[],
        )

    @staticmethod
    def _determine_completeness(row: ParsedSourceRow, *, management_style_row: bool) -> str:
        if row.value_band_raw is not None and row.value_aud is None:
            return "name_only"
        if row.value_aud is not None and management_style_row:
            return "value_only"
        if row.value_aud is not None and row.ownership_pct is not None:
            return "fully_disclosed"
        if row.value_aud is not None and row.security_identifier_value:
            return "fully_disclosed"
        if row.value_aud is not None and row.units is not None:
            return "fully_disclosed"
        if row.value_aud is not None and (row.classification_raw or row.address_raw or row.geo_lat is not None):
            return "fully_disclosed"
        if row.value_aud is not None:
            return "value_only"
        if row.ownership_pct is not None:
            return "ownership_only"
        return "name_only"

    @staticmethod
    def _first_non_null(rows: list[ParsedSourceRow], field_name: str):
        for row in rows:
            value = getattr(row, field_name)
            if value is not None:
                return value
        return None

    @staticmethod
    def _raw_payload_entry(row: ParsedSourceRow) -> dict[str, object]:
        return {
            "source_row_number": row.row_number,
            "payload": list(row.raw_payload),
        }

    @staticmethod
    def _sha256_of_payload(payload: list[str] | list[dict[str, object]]) -> str:
        digest = hashlib.sha256()
        digest.update(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        return digest.hexdigest()
