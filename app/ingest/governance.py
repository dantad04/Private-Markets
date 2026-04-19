from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.base import AdapterParseResult
from adapters.art_qsuper_mapping import EXPECTED_HEADER as ART_QSUPER_EXPECTED_HEADER
from adapters.aware_mapping import EXPECTED_TABLE_1_HEADER
from adapters.sunsuper_schema_mapping import EXPECTED_HEADER as SUNSUPER_SCHEMA_EXPECTED_HEADER
from app.db.models import AdapterMappingVersion, SchemaReviewQueue, SourceFile, TaxonomyMapping


AWARE_MAPPING_VERSION_ID = "aware-stage2-v1"
ART_QSUPER_MAPPING_VERSION_ID = "art-qsuper-stage2-v1"
ART_SUNSUPER_MAPPING_VERSION_ID = "art-sunsuper-stage2-v1"


class GovernanceError(Exception):
    """Base error for approved-mapping and schema-governance checks."""


class MissingApprovedMappingError(GovernanceError):
    pass


class SchemaDriftDetectedError(GovernanceError):
    pass


class UnapprovedTaxonomyMappingError(GovernanceError):
    pass


@dataclass(frozen=True)
class ApprovedTaxonomyMappingSeed:
    source_asset_class_raw: str
    source_filter_raw: str | None
    source_sub_filter_raw: str | None
    source_section_raw: str | None
    canonical_asset_class_code: str
    is_aggregate_default: bool
    disclosure_completeness_default: str | None
    notes: str | None


@dataclass(frozen=True)
class ApprovedAdapterMappingSeed:
    id: str
    adapter_key: str
    schema_fingerprint: str
    structural_expectations_json: dict[str, object]
    notes: str
    approved_by: str
    approved_at: datetime
    taxonomy_rows: tuple[ApprovedTaxonomyMappingSeed, ...]


AWARE_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=AWARE_MAPPING_VERSION_ID,
    adapter_key="AwarePhdAdapter",
    schema_fingerprint="0221ce01b8fb64d5b1ef06efaf5b70d8ffaf35cb2e0e163c5c0f4a54b4523139",
    structural_expectations_json={
        "observed_headers": EXPECTED_TABLE_1_HEADER,
        "observed_section_labels": [
            "ASSETS",
            "DERIVATIVES",
            "DERIVATIVES BY ASSET CLASS",
            "DERIVATIVES BY CURRENCY",
        ],
        "observed_tables": [1, 2, 3, 4],
        "observed_internal_external_values": ["EXTERNALLY", "INTERNALLY"],
        "observed_asset_classes": [
            "CASH",
            "FIXED INCOME",
            "FIXED INCOME (PRIVATE DEBT)",
            "LISTED EQUITY",
            "TOTAL INVESTMENT ITEMS",
            "UNLISTED EQUITY",
            "UNLISTED PROPERTY",
        ],
    },
    notes="Approved Stage 2 Aware synthetic vertical-slice mapping.",
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 19, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed("CASH", None, None, "ASSETS", "cash", False, None, "Table 1 direct holding"),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME", "INTERNALLY", None, "ASSETS", "fixed_income", False, None, "Table 1 direct holding"
        ),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME", "EXTERNALLY", None, "ASSETS", "fixed_income", False, None, "Table 1 manager rollup"
        ),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME (PRIVATE DEBT)",
            "INTERNALLY",
            None,
            "ASSETS",
            "private_debt",
            False,
            None,
            "Table 1 direct holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED EQUITY", None, None, "ASSETS", "listed_equity", False, None, "Table 1 direct holding"
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED EQUITY", "INTERNALLY", None, "ASSETS", "unlisted_equity", False, None, "Table 1 direct holding"
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED EQUITY", "EXTERNALLY", None, "ASSETS", "unlisted_equity", False, None, "Table 1 manager rollup"
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED PROPERTY",
            "INTERNALLY",
            None,
            "ASSETS",
            "unlisted_property",
            False,
            None,
            "Table 1 direct holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED PROPERTY",
            "EXTERNALLY",
            None,
            "ASSETS",
            "unlisted_property",
            False,
            None,
            "Table 1 manager rollup",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL CASH",
            None,
            None,
            "ASSETS",
            "cash",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL FIXED INCOME INTERNALLY",
            "INTERNALLY",
            None,
            "ASSETS",
            "fixed_income",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL FIXED INCOME (PRIVATE DEBT) INTERNALLY",
            "INTERNALLY",
            None,
            "ASSETS",
            "private_debt",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL FIXED INCOME EXTERNALLY",
            "EXTERNALLY",
            None,
            "ASSETS",
            "fixed_income",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL LISTED EQUITY",
            None,
            None,
            "ASSETS",
            "listed_equity",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL UNLISTED EQUITY INTERNALLY",
            "INTERNALLY",
            None,
            "ASSETS",
            "unlisted_equity",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL UNLISTED EQUITY EXTERNALLY",
            "EXTERNALLY",
            None,
            "ASSETS",
            "unlisted_equity",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL UNLISTED PROPERTY INTERNALLY",
            "INTERNALLY",
            None,
            "ASSETS",
            "unlisted_property",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL UNLISTED PROPERTY EXTERNALLY",
            "EXTERNALLY",
            None,
            "ASSETS",
            "unlisted_property",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "TOTAL INVESTMENT ITEMS",
            None,
            None,
            "ASSETS",
            "multi_asset_other",
            True,
            "aggregate_total",
            "Whole-file aggregate total",
        ),
    ),
)


ART_QSUPER_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=ART_QSUPER_MAPPING_VERSION_ID,
    adapter_key="ArtQsuperPhdAdapter",
    schema_fingerprint="42b9680ea59e47dd5753d4859fac412aefce8d91a2e6f50bfebe93e0717d4e79",
    structural_expectations_json={
        "observed_headers": ART_QSUPER_EXPECTED_HEADER,
        "observed_internal_external_values": ["Externally Managed", "Internally Managed"],
        "observed_asset_classes": [
            "Cash",
            "Cash Total",
            "Derivatives By AssetClass",
            "Derivatives By Currency",
            "Derivatives By Kind",
            "Fixed Income",
            "Listed Infrastructure",
            "Total Investment Items",
            "Unlisted Equity",
            "Unlisted Property",
        ],
    },
    notes="Approved Stage 2 ART-QSuper synthetic vertical-slice mapping.",
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 19, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed("Cash", None, None, None, "cash", False, None, "Direct cash row"),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Externally Managed",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Externally managed bond exposure",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            None,
            None,
            None,
            "listed_infrastructure",
            False,
            None,
            "Direct listed infrastructure row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Internally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Internally managed private equity exposure",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Externally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Externally managed private equity manager or vehicle row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Property",
            "Internally Managed",
            None,
            None,
            "unlisted_property",
            False,
            None,
            "Internally managed private property exposure",
        ),
        ApprovedTaxonomyMappingSeed(
            "Cash Total",
            None,
            None,
            None,
            "cash",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Total Investment Items",
            None,
            None,
            None,
            "multi_asset_other",
            True,
            "aggregate_total",
            "Whole-file aggregate total",
        ),
    ),
)


ART_SUNSUPER_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=ART_SUNSUPER_MAPPING_VERSION_ID,
    adapter_key="ArtSunsuperPhdAdapter",
    schema_fingerprint="212487dd7cc3263a5b3aa79f763c6f4f82a4a1b393751fb5cd7dbfc77e930ace",
    structural_expectations_json={
        "observed_headers": SUNSUPER_SCHEMA_EXPECTED_HEADER,
        "observed_asset_classes": [
            "Fixed Income",
            "Listed Equity",
            "Listed Infrastructure",
            "Private Equity",
        ],
        "observed_filters": [
            "All Assets",
            "Derivatives",
            "Externally Managed",
            "Private Equity",
        ],
        "observed_name_types": [
            "Asset",
            "Corporate",
            "Exposure",
            "Fund Vehicle",
            "Manager",
        ],
    },
    notes="Approved Stage 2 narrow ART-Sunsuper synthetic slice using the shared Sunsuper schema.",
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 19, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Externally Managed",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Manager-style value-bearing row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            "All Assets",
            None,
            None,
            "listed_infrastructure",
            False,
            None,
            "Direct all-assets row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            "Externally Managed",
            None,
            None,
            "listed_infrastructure",
            False,
            None,
            "Manager-style listed infrastructure row used for ambiguity review coverage",
        ),
        ApprovedTaxonomyMappingSeed(
            "Private Equity",
            "All Assets",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Ownership-only row on all-assets view",
        ),
        ApprovedTaxonomyMappingSeed(
            "Private Equity",
            "Private Equity",
            None,
            None,
            "unlisted_equity",
            False,
            "name_only",
            "Private-equity vehicle row",
        ),
    ),
)


APPROVED_MAPPING_SEEDS = {
    AWARE_APPROVED_MAPPING.adapter_key: AWARE_APPROVED_MAPPING,
    ART_QSUPER_APPROVED_MAPPING.adapter_key: ART_QSUPER_APPROVED_MAPPING,
    ART_SUNSUPER_APPROVED_MAPPING.adapter_key: ART_SUNSUPER_APPROVED_MAPPING,
}


def ensure_approved_mapping_seeded(session: Session, *, adapter_key: str) -> AdapterMappingVersion:
    seed = APPROVED_MAPPING_SEEDS.get(adapter_key)
    if seed is None:
        raise MissingApprovedMappingError(f"No approved mapping seed is configured for adapter {adapter_key!r}")

    mapping_version = session.get(AdapterMappingVersion, seed.id)
    if mapping_version is None:
        mapping_version = AdapterMappingVersion(
            id=seed.id,
            adapter_key=seed.adapter_key,
            schema_fingerprint=seed.schema_fingerprint,
            structural_expectations_json=seed.structural_expectations_json,
            notes=seed.notes,
            approved_by=seed.approved_by,
            approved_at=seed.approved_at,
            is_active=True,
        )
        session.add(mapping_version)
        session.flush()

    existing_rows = session.scalars(
        select(TaxonomyMapping).where(
            TaxonomyMapping.adapter_key == seed.adapter_key,
            TaxonomyMapping.mapping_version == seed.id,
        )
    ).all()
    if not existing_rows:
        for row in seed.taxonomy_rows:
            session.add(
                TaxonomyMapping(
                    adapter_key=seed.adapter_key,
                    mapping_version=seed.id,
                    source_asset_class_raw=row.source_asset_class_raw,
                    source_filter_raw=row.source_filter_raw,
                    source_sub_filter_raw=row.source_sub_filter_raw,
                    source_section_raw=row.source_section_raw,
                    canonical_asset_class_code=row.canonical_asset_class_code,
                    is_aggregate_default=row.is_aggregate_default,
                    disclosure_completeness_default=row.disclosure_completeness_default,
                    notes=row.notes,
                    approved_by=seed.approved_by,
                    approved_at=seed.approved_at,
                )
            )
        session.flush()

    return mapping_version


def enforce_approved_mapping(
    session: Session,
    *,
    source_file: SourceFile,
    parse_result: AdapterParseResult,
    raw_bytes: bytes,
    source_section_raw: str | None = None,
) -> str:
    mapping_version = ensure_approved_mapping_seeded(session, adapter_key=source_file.adapter_key)
    drift_summary = _build_structural_drift_summary(mapping_version, parse_result)
    if drift_summary:
        source_file.mapping_version_id = mapping_version.id
        source_file.ingest_status = "review_required"
        create_schema_review_queue_item(
            session,
            source_file=source_file,
            approved_mapping_version_id=mapping_version.id,
            review_reason="schema_drift",
            observed_schema_fingerprint=parse_result.schema_fingerprint,
            drift_summary_json=drift_summary,
            raw_bytes=raw_bytes,
        )
        session.flush()
        raise SchemaDriftDetectedError(
            f"{source_file.adapter_key} drift detected against approved mapping {mapping_version.id}"
        )

    taxonomy_summary = _build_taxonomy_validation_summary(
        session,
        mapping_version_id=mapping_version.id,
        parse_result=parse_result,
        source_section_raw=source_section_raw,
    )
    if taxonomy_summary:
        source_file.mapping_version_id = mapping_version.id
        source_file.ingest_status = "review_required"
        create_schema_review_queue_item(
            session,
            source_file=source_file,
            approved_mapping_version_id=mapping_version.id,
            review_reason="unapproved_taxonomy_mapping",
            observed_schema_fingerprint=parse_result.schema_fingerprint,
            drift_summary_json=taxonomy_summary,
            raw_bytes=raw_bytes,
        )
        session.flush()
        raise UnapprovedTaxonomyMappingError(
            f"{source_file.adapter_key} emitted rows not covered by approved taxonomy mapping {mapping_version.id}"
        )

    source_file.mapping_version_id = mapping_version.id
    return mapping_version.id


def create_schema_review_queue_item(
    session: Session,
    *,
    source_file: SourceFile,
    approved_mapping_version_id: str | None,
    review_reason: str,
    observed_schema_fingerprint: str | None,
    drift_summary_json: dict[str, object],
    raw_bytes: bytes,
) -> None:
    session.add(
        SchemaReviewQueue(
            adapter_key=source_file.adapter_key,
            source_file_id=source_file.id,
            source_url=source_file.source_url,
            checksum=source_file.checksum,
            observed_schema_fingerprint=observed_schema_fingerprint,
            approved_mapping_version_id=approved_mapping_version_id,
            review_reason=review_reason,
            status="open",
            drift_summary_json=drift_summary_json,
            sample_rows_json=_sample_rows(raw_bytes),
        )
    )


def _build_structural_drift_summary(
    mapping_version: AdapterMappingVersion,
    parse_result: AdapterParseResult,
) -> dict[str, object]:
    expected = mapping_version.structural_expectations_json
    actual = parse_result.structural_metadata
    summary: dict[str, object] = {}

    if parse_result.schema_fingerprint != mapping_version.schema_fingerprint:
        summary["schema_fingerprint"] = {
            "expected": mapping_version.schema_fingerprint,
            "actual": parse_result.schema_fingerprint,
        }

    for key in (
        "observed_headers",
        "observed_section_labels",
        "observed_tables",
        "observed_internal_external_values",
        "observed_asset_classes",
        "observed_filters",
        "observed_name_types",
    ):
        if expected.get(key) != actual.get(key):
            summary[key] = {
                "expected": expected.get(key),
                "actual": actual.get(key),
            }

    return summary


def _build_taxonomy_validation_summary(
    session: Session,
    *,
    mapping_version_id: str,
    parse_result: AdapterParseResult,
    source_section_raw: str | None,
) -> dict[str, object]:
    rows = session.scalars(
        select(TaxonomyMapping).where(TaxonomyMapping.mapping_version == mapping_version_id)
    ).all()
    # The taxonomy key is intentionally adapter-agnostic:
    # raw class label + optional adapter-specific qualifier + section + aggregate flag.
    # Aware uses section labels and management scope; ART-QSuper only uses the qualifier.
    mapping_lookup = {
        (
            row.source_asset_class_raw,
            row.source_filter_raw,
            row.source_section_raw,
            row.is_aggregate_default,
        ): row
        for row in rows
    }

    mismatches: list[dict[str, object]] = []
    for record in parse_result.holdings:
        mapping_row = mapping_lookup.get(
            (
                record.source_asset_class_raw,
                record.source_subclass_raw,
                source_section_raw,
                record.is_aggregate,
            )
        )
        if mapping_row is None:
            mismatches.append(
                {
                    "reason": "missing_mapping",
                    "source_row_number": record.source_row_number,
                    "source_asset_class_raw": record.source_asset_class_raw,
                    "source_subclass_raw": record.source_subclass_raw,
                    "is_aggregate": record.is_aggregate,
                }
            )
            continue
        if mapping_row.canonical_asset_class_code != record.canonical_asset_class_code:
            mismatches.append(
                {
                    "reason": "canonical_asset_class_mismatch",
                    "source_row_number": record.source_row_number,
                    "source_asset_class_raw": record.source_asset_class_raw,
                    "source_subclass_raw": record.source_subclass_raw,
                    "expected": mapping_row.canonical_asset_class_code,
                    "actual": record.canonical_asset_class_code,
                }
            )
        if mapping_row.disclosure_completeness_default and (
            mapping_row.disclosure_completeness_default != record.disclosure_completeness
        ):
            mismatches.append(
                {
                    "reason": "disclosure_completeness_mismatch",
                    "source_row_number": record.source_row_number,
                    "source_asset_class_raw": record.source_asset_class_raw,
                    "expected": mapping_row.disclosure_completeness_default,
                    "actual": record.disclosure_completeness,
                }
            )

    if not mismatches:
        return {}
    return {"taxonomy_mismatches": mismatches[:10]}


def _sample_rows(raw_bytes: bytes) -> list[list[str]]:
    rows = list(csv.reader(io.StringIO(raw_bytes.decode("utf-8", errors="replace"))))
    samples: list[list[str]] = []
    for row in rows:
        if not any(cell.strip() for cell in row):
            continue
        samples.append(row)
        if len(samples) == 20:
            break
    return samples
