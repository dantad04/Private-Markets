from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
import hashlib
import io
import json

from adapters.art_qsuper_errors import (
    EmptyFileError,
    HeaderMismatchError,
    MalformedRowError,
    MultipleDatesError,
    MultipleOptionsError,
    UnknownAssetClassError,
)
from adapters.art_qsuper_mapping import EXPECTED_HEADER, lookup_asset_class_mapping
from adapters.art_qsuper_normalisation import (
    clean_cell,
    decode_utf8,
    infer_identifier_type,
    parse_dollar_amount,
    parse_numeric,
    parse_optional_text,
    parse_percent,
    parse_textual_date,
)
from adapters.base import AdapterParseResult, SourceFileMetadata, SourceNormalisedHoldingRecord


class ArtQsuperPhdAdapter:
    adapter_key = "ArtQsuperPhdAdapter"
    PORTFOLIO_POSTURE_ASSET_CLASSES = {
        "derivatives by kind",
        "derivatives by assetclass",
        "derivatives by asset class",
        "derivatives by currency",
    }

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
        skipped_portfolio_posture_rows = 0

        for row_number, raw_row in enumerate(rows[1:], start=2):
            raw_payload = list(raw_row)
            cleaned_row = [clean_cell(cell) for cell in raw_payload]
            if not any(cleaned_row):
                continue
            if len(cleaned_row) != len(EXPECTED_HEADER):
                raise MalformedRowError(row_number, f"expected 16 columns, got {len(cleaned_row)}")

            (
                reporting_date_raw,
                option_raw,
                asset_class_raw,
                internal_external_raw,
                investment_name_raw,
                security_identifier_raw,
                currency_raw,
                units_raw,
                value_raw,
                weighting_raw,
                ownership_raw,
                address_raw,
                classification_raw,
                location_raw,
                value_band_raw,
                _notes_raw,
            ) = raw_payload

            reporting_date_value = clean_cell(reporting_date_raw)
            option_value = clean_cell(option_raw)
            asset_class_value = clean_cell(asset_class_raw)
            internal_external_value = parse_optional_text(internal_external_raw)

            if reporting_date_value == "":
                raise MalformedRowError(row_number, "missing AsAtDate")
            if option_value == "":
                raise MalformedRowError(row_number, "missing OptionName")
            if asset_class_value == "":
                raise MalformedRowError(row_number, "missing AssetClass")

            observed_options.add(option_value)
            observed_dates.add(reporting_date_value)
            observed_asset_classes.add(asset_class_value)
            if internal_external_value is not None:
                observed_internal_external_values.add(internal_external_value)

            if self._is_portfolio_posture_row(asset_class_value):
                skipped_portfolio_posture_rows += 1
                continue

            mapping = lookup_asset_class_mapping(asset_class_value)
            if mapping is None:
                raise UnknownAssetClassError(row_number, asset_class_value, internal_external_value)

            reporting_date = parse_textual_date(reporting_date_value, row_number)
            raw_name = parse_optional_text(investment_name_raw)
            security_identifier_value = parse_optional_text(security_identifier_raw)
            currency = parse_optional_text(currency_raw)
            units = parse_numeric(units_raw, row_number, "UnitsHeld")
            value_aud = parse_dollar_amount(value_raw, row_number, "MarketValueAud")
            weighting_pct = parse_percent(weighting_raw, row_number, "WeightingPct")
            ownership_pct = parse_percent(ownership_raw, row_number, "OwnershipPct")
            address = parse_optional_text(address_raw)
            classification = parse_optional_text(classification_raw)
            location = parse_optional_text(location_raw)
            value_band = parse_optional_text(value_band_raw)
            security_identifier_type = infer_identifier_type(security_identifier_value)

            if mapping.is_aggregate:
                raw_name = None
                disclosure_completeness = "aggregate_total"
            else:
                if raw_name is None:
                    raise MalformedRowError(row_number, "non-aggregate row with empty InvestmentName")
                disclosure_completeness = self._determine_completeness(
                    value_aud=value_aud,
                    ownership_pct=ownership_pct,
                    units=units,
                    security_identifier_value=security_identifier_value,
                    address_raw=address,
                    classification_raw=classification,
                    value_band_raw=value_band,
                    raw_name=raw_name,
                )

            emitted.append(
                SourceNormalisedHoldingRecord(
                    source_file_id=source_file_metadata.source_file_id,
                    source_fund_id=source_file_metadata.fund_id,
                    source_option_code=option_value,
                    source_option_name_raw=option_value,
                    reporting_period_date=reporting_date,
                    source_asset_class_raw=asset_class_value,
                    source_subclass_raw=internal_external_value,
                    canonical_asset_class_code=mapping.canonical_code,
                    is_aggregate=mapping.is_aggregate,
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
                    classification_raw=classification,
                    location_raw=location,
                    value_band_raw=value_band,
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
            "skipped_portfolio_posture_rows": skipped_portfolio_posture_rows,
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
        address_raw: str | None,
        classification_raw: str | None,
        value_band_raw: str | None,
        raw_name: str | None,
    ) -> str:
        if value_band_raw is not None and value_aud is None:
            return "name_only"
        if value_aud is not None and ownership_pct is not None:
            return "fully_disclosed"
        if value_aud is not None and security_identifier_value:
            return "fully_disclosed"
        if value_aud is not None and units is not None:
            return "fully_disclosed"
        if value_aud is not None and (address_raw or classification_raw):
            return "fully_disclosed"
        if value_aud is not None:
            return "value_only"
        if ownership_pct is not None:
            return "ownership_only"
        if raw_name:
            return "name_only"
        return "name_only"

    @classmethod
    def _is_portfolio_posture_row(cls, asset_class_raw: str) -> bool:
        return asset_class_raw.strip().casefold() in cls.PORTFOLIO_POSTURE_ASSET_CLASSES

    @staticmethod
    def _sha256_of_row(raw_row: list[str]) -> str:
        digest = hashlib.sha256()
        digest.update(json.dumps(raw_row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        return digest.hexdigest()
