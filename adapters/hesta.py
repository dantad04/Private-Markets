from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from decimal import Decimal
import hashlib
import io
import json

from adapters.base import AdapterParseResult, SourceFileMetadata, SourceNormalisedHoldingRecord
from adapters.hesta_errors import (
    EmptyFileError,
    HeaderMismatchError,
    MalformedRowError,
    MultipleDatesError,
    MultipleOptionsError,
    UnknownAssetClassError,
)
from adapters.hesta_mapping import EXPECTED_HEADER, lookup_asset_class_mapping
from adapters.hesta_normalisation import (
    assert_not_unexpected_null_token,
    clean_cell,
    decode_utf8,
    infer_identifier_type,
    parse_numeric,
    parse_percent,
    parse_uk_date,
)


class HestaPhdAdapter:
    adapter_key = "HestaPhdAdapter"

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
        if len(rows) < 2:
            raise EmptyFileError("Expected header plus at least one data row")

        header = [clean_cell(cell) for cell in rows[0]]
        if header != EXPECTED_HEADER:
            raise HeaderMismatchError(f"Expected {EXPECTED_HEADER!r}, received {header!r}")

        emitted: list[SourceNormalisedHoldingRecord] = []
        observed_options: set[str] = set()
        observed_dates: set[str] = set()
        observed_asset_classes: set[str] = set()
        observed_internal_external_values: set[str] = set()

        for row_number, raw_row in enumerate(rows[1:], start=2):
            raw_payload = list(raw_row)
            cleaned_row = [clean_cell(cell) for cell in raw_payload]
            if not any(cleaned_row):
                continue
            if len(cleaned_row) != len(EXPECTED_HEADER):
                raise MalformedRowError(row_number, f"expected 11 columns, got {len(cleaned_row)}")

            (
                effective_date_raw,
                option_raw,
                asset_class_raw,
                internal_external_raw,
                name_raw,
                units_raw,
                value_raw,
                weighting_raw,
                ownership_raw,
                currency_raw,
                security_id_raw,
            ) = cleaned_row

            assert_not_unexpected_null_token(option_raw, row_number, "Option")
            assert_not_unexpected_null_token(asset_class_raw, row_number, "Asset Class")
            assert_not_unexpected_null_token(internal_external_raw, row_number, "Internal/External")
            assert_not_unexpected_null_token(name_raw, row_number, "Name/kind of investment item")
            assert_not_unexpected_null_token(currency_raw, row_number, "Currency")
            assert_not_unexpected_null_token(security_id_raw, row_number, "Security Identifier")

            if option_raw == "":
                raise MalformedRowError(row_number, "missing option")
            if effective_date_raw == "":
                raise MalformedRowError(row_number, "missing effective date")
            if asset_class_raw == "":
                raise MalformedRowError(row_number, "missing asset class")

            observed_options.add(option_raw)
            observed_dates.add(effective_date_raw)
            observed_asset_classes.add(asset_class_raw)
            if internal_external_raw:
                observed_internal_external_values.add(internal_external_raw)

            mapping = lookup_asset_class_mapping(asset_class_raw, internal_external_raw or None)
            if mapping is None:
                raise UnknownAssetClassError(row_number, asset_class_raw, internal_external_raw or None)

            effective_date = parse_uk_date(effective_date_raw, row_number)
            units = parse_numeric(units_raw, row_number, "Units")
            value_aud = parse_numeric(value_raw, row_number, "Value (AUD)")
            weighting = parse_numeric(weighting_raw, row_number, "Weighting")
            ownership_pct = parse_percent(
                ownership_raw,
                row_number,
                "% Ownership / Property Held",
            )
            security_identifier_type = infer_identifier_type(security_id_raw)

            parse_warning_flags: list[str] = []
            if weighting is not None and value_aud is None:
                warning = f"row {row_number}: weighting populated but value is empty"
                parse_warning_flags.append("weighting_without_value")
                warnings.append(warning)
            if ownership_pct == Decimal("0"):
                warning = f"row {row_number}: ownership percent is zero"
                parse_warning_flags.append("zero_ownership_pct")
                warnings.append(warning)
            if value_aud is not None and value_aud < 0:
                # Verified Hesta cash rows include negative balances, so warn rather than raise.
                warning = f"row {row_number}: negative value_aud"
                parse_warning_flags.append("negative_value_aud")
                warnings.append(warning)

            if mapping.is_aggregate:
                raw_name = None
                disclosure_completeness = "aggregate_total"
            else:
                if name_raw == "":
                    raise MalformedRowError(row_number, "non-aggregate row with empty name")
                raw_name = name_raw
                disclosure_completeness = self._determine_completeness(
                    value_aud=value_aud,
                    ownership_pct=ownership_pct,
                    units=units,
                    security_identifier_value=security_id_raw or None,
                    raw_name=raw_name,
                )

            emitted.append(
                SourceNormalisedHoldingRecord(
                    source_file_id=source_file_metadata.source_file_id,
                    source_fund_id=source_file_metadata.fund_id,
                    source_option_code=option_raw,
                    source_option_name_raw=option_raw,
                    reporting_period_date=effective_date,
                    source_asset_class_raw=asset_class_raw,
                    source_subclass_raw=internal_external_raw or None,
                    canonical_asset_class_code=mapping.canonical_code,
                    is_aggregate=mapping.is_aggregate,
                    raw_name=raw_name,
                    value_aud=value_aud,
                    ownership_pct=ownership_pct,
                    units=units,
                    weighting_pct=weighting,
                    currency_raw=currency_raw or None,
                    security_identifier_value=security_id_raw or None,
                    security_identifier_type=security_identifier_type,
                    address_raw=None,
                    geo_lat=None,
                    geo_lng=None,
                    classification_raw=None,
                    location_raw=None,
                    value_band_raw=None,
                    disclosure_completeness=disclosure_completeness,
                    source_row_number=row_number,
                    source_row_hash=self._sha256_of_row(raw_payload),
                    raw_payload_json=raw_payload,
                    parse_warning_flags=parse_warning_flags,
                    metadata_attached_from_row_numbers=[],
                )
            )

        if len(observed_options) != 1:
            raise MultipleOptionsError(sorted(observed_options))
        if len(observed_dates) != 1:
            raise MultipleDatesError(sorted(observed_dates))

        asset_class_counts = Counter(record.canonical_asset_class_code for record in emitted)
        completeness_counts = Counter(record.disclosure_completeness for record in emitted)

        structural_metadata = {
            "observed_headers": header,
            "observed_asset_classes": sorted(observed_asset_classes),
            "observed_options": sorted(observed_options),
            "observed_reporting_dates": sorted(observed_dates),
            "observed_internal_external_values": sorted(observed_internal_external_values),
            "total_rows_read": len(rows),
            "total_rows_emitted": len(emitted),
            "total_rows_aggregate": sum(1 for record in emitted if record.is_aggregate),
            "encoding_replacement_count": replacement_count,
            "unknown_asset_class_values": [],
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
                    "internal_external_values": sorted(observed_internal_external_values),
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
    def _determine_completeness(
        *,
        value_aud: Decimal | None,
        ownership_pct: Decimal | None,
        units: Decimal | None,
        security_identifier_value: str | None,
        raw_name: str | None,
    ) -> str:
        # The verified Hesta fixture only discloses ownership on internally managed rows.
        # If a future Hesta file emits externally managed rows with ownership populated,
        # the adapter should be reviewed rather than silently reinterpreted here.
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
