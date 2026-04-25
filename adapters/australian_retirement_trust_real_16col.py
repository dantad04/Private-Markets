from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
import hashlib
import io
import json
from urllib.parse import urlparse

from adapters.australian_retirement_trust_real_16col_errors import (
    EmptyFileError,
    FundIdentityMismatchError,
    HeaderMismatchError,
    MalformedRowError,
    MultipleDatesError,
    MultipleOptionsError,
    SchemaFingerprintMismatchError,
    SourceDomainMismatchError,
    UnexpectedDerivativePostureCountError,
    UnknownAssetClassError,
    UnapprovedReportingPeriodError,
)
from adapters.australian_retirement_trust_real_16col_mapping import (
    ADAPTER_KEY,
    AGGREGATE_TOTAL_TYPES,
    APPROVED_REPORTING_DATE,
    APPROVED_REPORTING_DATE_RAW,
    APPROVED_SCHEMA_FINGERPRINT,
    APPROVED_TYPE_VALUES,
    DERIVATIVE_POSTURE_TYPES,
    EXPECTED_DERIVATIVE_POSTURE_ROWS_PER_FILE,
    EXPECTED_HEADER,
    derive_friendly_option_name,
    is_derivative_posture_type,
    lookup_asset_class_mapping,
)
from adapters.australian_retirement_trust_real_16col_normalisation import (
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


class AustralianRetirementTrustReal16ColumnPhdAdapter:
    adapter_key = ADAPTER_KEY

    def parse(
        self,
        source_file_metadata: SourceFileMetadata,
        raw_bytes: bytes,
        approved_mapping_config: dict[str, object] | None = None,
    ) -> AdapterParseResult:
        del approved_mapping_config

        source_identity_metadata = self._validate_source_identity(source_file_metadata)
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

        schema_fingerprint = self._schema_fingerprint(raw_bytes)
        if schema_fingerprint != APPROVED_SCHEMA_FINGERPRINT:
            raise SchemaFingerprintMismatchError(APPROVED_SCHEMA_FINGERPRINT, schema_fingerprint)

        emitted: list[SourceNormalisedHoldingRecord] = []
        observed_options: set[str] = set()
        observed_option_names: set[str] = set()
        observed_dates: set[str] = set()
        observed_types: set[str] = set()
        skipped_derivative_posture_counts: Counter[str] = Counter()

        for row_number, raw_row in enumerate(rows[1:], start=2):
            raw_payload = list(raw_row)
            cleaned_row = [clean_cell(cell) for cell in raw_payload]
            if not any(cleaned_row):
                continue
            if len(cleaned_row) != len(EXPECTED_HEADER):
                raise MalformedRowError(row_number, f"expected 16 columns, got {len(cleaned_row)}")

            row = dict(zip(EXPECTED_HEADER, cleaned_row, strict=True))
            reporting_date_raw = row["AsAtDate"]
            option_name_raw = row["OptionName"]
            type_value = row["Type"]

            if reporting_date_raw == "":
                raise MalformedRowError(row_number, "missing AsAtDate")
            if option_name_raw == "":
                raise MalformedRowError(row_number, "missing OptionName")
            if type_value == "":
                raise MalformedRowError(row_number, "missing Type")

            observed_options.add(option_name_raw)
            observed_option_names.add(derive_friendly_option_name(option_name_raw))
            observed_dates.add(reporting_date_raw)
            observed_types.add(type_value)

            reporting_date = parse_textual_date(reporting_date_raw, row_number)

            if is_derivative_posture_type(type_value):
                skipped_derivative_posture_counts[type_value] += 1
                continue

            mapping = lookup_asset_class_mapping(type_value)
            if mapping is None:
                raise UnknownAssetClassError(row_number, type_value)

            is_aggregate = self._is_aggregate_row(row)
            if is_aggregate:
                value_aud = parse_dollar_amount(row["TotalValue"], row_number, "TotalValue")
                weighting_pct = parse_percent(row["TotalWeighting"], row_number, "TotalWeighting")
                raw_name = None
                ownership_pct = None
                units = None
                currency = None
                security_identifier_value = None
                security_identifier_type = None
                address = None
                disclosure_completeness = "aggregate_total"
            else:
                raw_name = parse_optional_text(row["Name"])
                if raw_name is None:
                    raise MalformedRowError(row_number, "non-aggregate row with empty Name")
                value_aud = parse_dollar_amount(row["Value"], row_number, "Value")
                weighting_pct = parse_percent(row["Weighting"], row_number, "Weighting")
                ownership_pct = parse_percent(row["Ownership"], row_number, "Ownership")
                units = parse_numeric(row["UnitsHeld"], row_number, "UnitsHeld")
                currency = parse_optional_text(row["Currency"])
                security_identifier_value = parse_optional_text(row["SecurityIdentifier"])
                security_identifier_type = infer_identifier_type(security_identifier_value)
                address = parse_optional_text(row["Address"])
                disclosure_completeness = self._determine_completeness(
                    value_aud=value_aud,
                    weighting_pct=weighting_pct,
                    ownership_pct=ownership_pct,
                    units=units,
                    security_identifier_value=security_identifier_value,
                    raw_name=raw_name,
                )

            emitted.append(
                SourceNormalisedHoldingRecord(
                    source_file_id=source_file_metadata.source_file_id,
                    source_fund_id=source_file_metadata.fund_id,
                    source_option_code=None,
                    source_option_name_raw=derive_friendly_option_name(option_name_raw),
                    reporting_period_date=reporting_date,
                    source_asset_class_raw=type_value,
                    source_subclass_raw=None,
                    canonical_asset_class_code=mapping.canonical_code,
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
        if observed_dates != {APPROVED_REPORTING_DATE_RAW}:
            raise UnapprovedReportingPeriodError(sorted(observed_dates))
        if any(record.reporting_period_date != APPROVED_REPORTING_DATE for record in emitted):
            raise UnapprovedReportingPeriodError(sorted(observed_dates))

        skipped_derivative_posture_rows = sum(skipped_derivative_posture_counts.values())
        if skipped_derivative_posture_rows != EXPECTED_DERIVATIVE_POSTURE_ROWS_PER_FILE:
            raise UnexpectedDerivativePostureCountError(skipped_derivative_posture_rows)

        asset_class_counts = Counter(record.canonical_asset_class_code for record in emitted)
        completeness_counts = Counter(record.disclosure_completeness for record in emitted)

        structural_metadata = {
            "observed_headers": header,
            "observed_asset_classes": list(APPROVED_TYPE_VALUES),
            "observed_types": sorted(observed_types),
            "observed_options": sorted(observed_options),
            "observed_option_names": sorted(observed_option_names),
            "observed_reporting_dates": sorted(observed_dates),
            "total_rows_read": len(rows),
            "total_rows_emitted": len(emitted),
            "total_rows_aggregate": sum(1 for record in emitted if record.is_aggregate),
            "encoding_replacement_count": replacement_count,
            "skipped_portfolio_posture_rows": skipped_derivative_posture_rows,
            "skipped_portfolio_posture_rows_by_type": dict(sorted(skipped_derivative_posture_counts.items())),
            "unknown_asset_class_values": [],
            **source_identity_metadata,
        }
        parse_statistics = {
            **structural_metadata,
            "canonical_asset_class_counts": dict(sorted(asset_class_counts.items())),
            "disclosure_completeness_counts": dict(sorted(completeness_counts.items())),
        }

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
        weighting_pct: Decimal | None,
        ownership_pct: Decimal | None,
        units: Decimal | None,
        security_identifier_value: str | None,
        raw_name: str | None,
    ) -> str:
        if value_aud is not None and weighting_pct is not None and (security_identifier_value or units is not None):
            return "fully_disclosed"
        if value_aud is not None and weighting_pct is not None:
            return "value_only"
        if value_aud is not None:
            return "value_only"
        if ownership_pct is not None:
            return "ownership_only"
        if raw_name:
            return "name_only"
        raise ValueError("Cannot determine disclosure completeness for unnamed empty row")

    @staticmethod
    def _is_aggregate_row(row: dict[str, str]) -> bool:
        if row["Type"] in AGGREGATE_TOTAL_TYPES:
            return True
        return (
            row["Type"] not in DERIVATIVE_POSTURE_TYPES
            and row["Name"].casefold() == "n/a"
            and row["Value"] == ""
            and row["Weighting"] == ""
            and row["TotalValue"] != ""
            and row["TotalWeighting"] != ""
        )

    @staticmethod
    def _schema_fingerprint(raw_bytes: bytes) -> str:
        first_line = raw_bytes.split(b"\n", 1)[0].rstrip(b"\r")
        return hashlib.sha256(first_line).hexdigest()

    @staticmethod
    def _sha256_of_row(raw_row: list[str]) -> str:
        digest = hashlib.sha256()
        digest.update(json.dumps(raw_row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _validate_source_identity(source_file_metadata: SourceFileMetadata) -> dict[str, str | None]:
        fund_code = source_file_metadata.fund_code
        if fund_code is not None and fund_code.casefold() not in {"art", "australian_retirement_trust"}:
            raise FundIdentityMismatchError(fund_code)

        parsed = urlparse(source_file_metadata.source_url)
        if parsed.scheme in {"http", "https"}:
            domain = parsed.hostname.casefold() if parsed.hostname else None
            if domain != "files.australianretirementtrust.com.au" or not parsed.path.startswith("/phd/super/"):
                raise SourceDomainMismatchError(source_file_metadata.source_url)
            return {
                "source_domain": domain,
                "source_domain_verification": "official_art_phd_super_source_url",
            }

        return {
            "source_domain": None,
            "source_domain_verification": "not_applicable_local_path",
        }
