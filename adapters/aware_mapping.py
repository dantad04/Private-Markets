from __future__ import annotations

from dataclasses import dataclass


EXPECTED_TABLE_1_HEADER = [
    "ASSET CLASS",
    "INTERNALLY MANAGED OR EXTERNALLY MANAGED",
    "NAME OF INSTITUTION",
    "NAME OF ISSUER / COUNTERPARTY",
    "NAME OF FUND MANAGER",
    "NAME / KIND OF INVESTMENT ITEM",
    "CURRENCY",
    "SECURITY IDENTIFIER",
    "ADDRESS",
    "% OWNERSHIP / PROPERTY HELD",
    "UNITS HELD",
    "VALUE(AUD)",
    "WEIGHTING(%)",
    "",
]

INSTITUTION_COLUMN = "institution"
ISSUER_COLUMN = "issuer_counterparty"
FUND_MANAGER_COLUMN = "fund_manager"
NAME_KIND_COLUMN = "name_kind"


@dataclass(frozen=True)
class AggregateInfo:
    base_asset_class: str
    source_subclass_raw: str | None


BASE_ASSET_CLASS_TO_CANONICAL = {
    "CASH": "cash",
    "FIXED INCOME": "fixed_income",
    "FIXED INCOME (PRIVATE DEBT)": "private_debt",
    "LISTED EQUITY": "listed_equity",
    "UNLISTED EQUITY": "unlisted_equity",
    "LISTED PROPERTY": "listed_property",
    "UNLISTED PROPERTY": "unlisted_property",
    "LISTED INFRASTRUCTURE": "listed_infrastructure",
    "UNLISTED INFRASTRUCTURE": "unlisted_infrastructure",
    "LISTED ALTERNATIVES": "alternatives",
    "UNLISTED ALTERNATIVES": "alternatives",
    "TOTAL INVESTMENT ITEMS": "multi_asset_other",
}


NAME_SELECTION_RULES = {
    ("CASH", None): (INSTITUTION_COLUMN,),
    ("FIXED INCOME", "INTERNALLY"): (ISSUER_COLUMN,),
    ("FIXED INCOME", "EXTERNALLY"): (FUND_MANAGER_COLUMN,),
    ("FIXED INCOME (PRIVATE DEBT)", "INTERNALLY"): (ISSUER_COLUMN,),
    ("FIXED INCOME (PRIVATE DEBT)", "EXTERNALLY"): (FUND_MANAGER_COLUMN,),
    ("LISTED EQUITY", None): (NAME_KIND_COLUMN,),
    ("LISTED PROPERTY", None): (NAME_KIND_COLUMN,),
    ("LISTED INFRASTRUCTURE", None): (NAME_KIND_COLUMN,),
    ("UNLISTED EQUITY", "INTERNALLY"): (NAME_KIND_COLUMN,),
    ("UNLISTED EQUITY", "EXTERNALLY"): (FUND_MANAGER_COLUMN,),
    ("UNLISTED PROPERTY", "INTERNALLY"): (NAME_KIND_COLUMN,),
    ("UNLISTED PROPERTY", "EXTERNALLY"): (FUND_MANAGER_COLUMN,),
    ("UNLISTED INFRASTRUCTURE", "INTERNALLY"): (NAME_KIND_COLUMN,),
    ("UNLISTED INFRASTRUCTURE", "EXTERNALLY"): (FUND_MANAGER_COLUMN,),
}

FALLBACK_NAME_SELECTION = (
    NAME_KIND_COLUMN,
    ISSUER_COLUMN,
    INSTITUTION_COLUMN,
    FUND_MANAGER_COLUMN,
)


def lookup_canonical_asset_class(base_asset_class: str) -> str | None:
    return BASE_ASSET_CLASS_TO_CANONICAL.get(base_asset_class)


def parse_aggregate_label(value: str) -> AggregateInfo | None:
    stripped = value.strip()
    if stripped == "TOTAL INVESTMENT ITEMS":
        return AggregateInfo(base_asset_class=stripped, source_subclass_raw=None)
    if not stripped.startswith("SUB TOTAL "):
        return None

    remainder = stripped[len("SUB TOTAL ") :]
    for suffix in (" INTERNALLY", " EXTERNALLY"):
        if remainder.endswith(suffix):
            return AggregateInfo(
                base_asset_class=remainder[: -len(suffix)],
                source_subclass_raw=suffix.strip(),
            )
    return AggregateInfo(base_asset_class=remainder, source_subclass_raw=None)


def select_name_columns(base_asset_class: str, source_subclass_raw: str | None) -> tuple[str, ...]:
    direct = NAME_SELECTION_RULES.get((base_asset_class, source_subclass_raw))
    if direct is not None:
        return direct
    direct = NAME_SELECTION_RULES.get((base_asset_class, None))
    if direct is not None:
        return direct
    return FALLBACK_NAME_SELECTION
