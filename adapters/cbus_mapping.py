from __future__ import annotations

from dataclasses import dataclass


EXPECTED_HEADER = [
    "Section",
    "Table Order",
    "Security Name",
    "Portfolio Name",
    "Manager Name",
    "Issuer",
    "Institution",
    "Security Identifier",
    "Ownership%",
    "Address",
    "Local Currency",
    "Units Held",
    "Market Value",
    "Weight",
]

SECURITY_NAME_COLUMN = "security_name"
PORTFOLIO_NAME_COLUMN = "portfolio_name"
MANAGER_NAME_COLUMN = "manager_name"
ISSUER_COLUMN = "issuer"
INSTITUTION_COLUMN = "institution"


@dataclass(frozen=True)
class CbusSectionMapping:
    source_asset_class_raw: str
    canonical_asset_class_code: str
    source_subclass_raw: str | None
    name_column: str | None
    is_aggregate: bool = False


SECTION_MAPPINGS = {
    "Cash": CbusSectionMapping("Cash", "cash", None, INSTITUTION_COLUMN),
    "Fixed income internal": CbusSectionMapping("Fixed income internal", "fixed_income", "internal", ISSUER_COLUMN),
    "Fixed Income External": CbusSectionMapping("Fixed Income External", "fixed_income", "external", MANAGER_NAME_COLUMN),
    "Fixed income internal(PRIVATE DEBT)": CbusSectionMapping(
        "Fixed income internal(PRIVATE DEBT)",
        "private_debt",
        "internal",
        ISSUER_COLUMN,
    ),
    "Listed equities": CbusSectionMapping("Listed equities", "listed_equity", None, SECURITY_NAME_COLUMN),
    "Unlisted equities internal": CbusSectionMapping(
        "Unlisted equities internal",
        "unlisted_equity",
        "internal",
        PORTFOLIO_NAME_COLUMN,
    ),
    "Unlisted equities external": CbusSectionMapping(
        "Unlisted equities external",
        "unlisted_equity",
        "external",
        MANAGER_NAME_COLUMN,
    ),
    "Listed property": CbusSectionMapping("Listed property", "listed_property", None, SECURITY_NAME_COLUMN),
    "Unlisted property internal": CbusSectionMapping(
        "Unlisted property internal",
        "unlisted_property",
        "internal",
        PORTFOLIO_NAME_COLUMN,
    ),
    "Unlisted property external": CbusSectionMapping(
        "Unlisted property external",
        "unlisted_property",
        "external",
        MANAGER_NAME_COLUMN,
    ),
    "Listed infrastructure": CbusSectionMapping("Listed infrastructure", "listed_infrastructure", None, SECURITY_NAME_COLUMN),
    "Unlisted infrastructure internal": CbusSectionMapping(
        "Unlisted infrastructure internal",
        "unlisted_infrastructure",
        "internal",
        PORTFOLIO_NAME_COLUMN,
    ),
    "Unlisted infrastructure external": CbusSectionMapping(
        "Unlisted infrastructure external",
        "unlisted_infrastructure",
        "external",
        MANAGER_NAME_COLUMN,
    ),
    "Unlisted alternatives internal": CbusSectionMapping(
        "Unlisted alternatives internal",
        "alternatives",
        "internal",
        PORTFOLIO_NAME_COLUMN,
    ),
    "Unlisted alternatives external": CbusSectionMapping(
        "Unlisted alternatives external",
        "alternatives",
        "external",
        MANAGER_NAME_COLUMN,
    ),
}

TOTAL_SECTION_MAPPINGS = {
    "Cash TOTAL": CbusSectionMapping("Cash TOTAL", "cash", None, None, is_aggregate=True),
    "Fixed income internal TOTAL": CbusSectionMapping(
        "Fixed income internal TOTAL",
        "fixed_income",
        "internal",
        None,
        is_aggregate=True,
    ),
    "Fixed income external TOTAL": CbusSectionMapping(
        "Fixed income external TOTAL",
        "fixed_income",
        "external",
        None,
        is_aggregate=True,
    ),
    "Listed equities TOTAL": CbusSectionMapping("Listed equities TOTAL", "listed_equity", None, None, is_aggregate=True),
    "Unlisted equities internal TOTAL": CbusSectionMapping(
        "Unlisted equities internal TOTAL",
        "unlisted_equity",
        "internal",
        None,
        is_aggregate=True,
    ),
    "Unlisted equities external TOTAL": CbusSectionMapping(
        "Unlisted equities external TOTAL",
        "unlisted_equity",
        "external",
        None,
        is_aggregate=True,
    ),
    "Listed property TOTAL": CbusSectionMapping("Listed property TOTAL", "listed_property", None, None, is_aggregate=True),
    "Unlisted property internal TOTAL": CbusSectionMapping(
        "Unlisted property internal TOTAL",
        "unlisted_property",
        "internal",
        None,
        is_aggregate=True,
    ),
    "Unlisted property external TOTAL": CbusSectionMapping(
        "Unlisted property external TOTAL",
        "unlisted_property",
        "external",
        None,
        is_aggregate=True,
    ),
    "Listed infrastructure TOTAL": CbusSectionMapping(
        "Listed infrastructure TOTAL",
        "listed_infrastructure",
        None,
        None,
        is_aggregate=True,
    ),
    "Unlisted infrastructure internal TOTAL": CbusSectionMapping(
        "Unlisted infrastructure internal TOTAL",
        "unlisted_infrastructure",
        "internal",
        None,
        is_aggregate=True,
    ),
    "Unlisted infrastructure external TOTAL": CbusSectionMapping(
        "Unlisted infrastructure external TOTAL",
        "unlisted_infrastructure",
        "external",
        None,
        is_aggregate=True,
    ),
    "Unlisted alternatives internal TOTAL": CbusSectionMapping(
        "Unlisted alternatives internal TOTAL",
        "alternatives",
        "internal",
        None,
        is_aggregate=True,
    ),
    "Unlisted alternatives external TOTAL": CbusSectionMapping(
        "Unlisted alternatives external TOTAL",
        "alternatives",
        "external",
        None,
        is_aggregate=True,
    ),
    "Table 1 TOTAL": CbusSectionMapping("Table 1 TOTAL", "multi_asset_other", None, None, is_aggregate=True),
}

SECTION_LABEL_ALIASES = {
    "Fixed income external": "Fixed Income External",
}


def lookup_section_mapping(section_label: str) -> CbusSectionMapping | None:
    direct_mapping = SECTION_MAPPINGS.get(section_label) or TOTAL_SECTION_MAPPINGS.get(section_label)
    if direct_mapping is not None:
        return direct_mapping
    alias = SECTION_LABEL_ALIASES.get(section_label)
    if alias is None:
        return None
    return SECTION_MAPPINGS.get(alias) or TOTAL_SECTION_MAPPINGS.get(alias)
