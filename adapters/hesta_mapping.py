from __future__ import annotations

from dataclasses import dataclass


EXPECTED_HEADER = [
    "Effective Date",
    "Option",
    "Asset Class",
    "Internal/External",
    "Name/kind of investment item",
    "Units",
    "Value (AUD)",
    "Weighting",
    "% Ownership / Property Held",
    "Currency",
    "Security Identifier",
]


@dataclass(frozen=True)
class AssetClassMappingRule:
    canonical_code: str
    is_aggregate: bool


def _key(asset_class: str, internal_external: str | None = None) -> tuple[str, str]:
    return (asset_class.strip().casefold(), (internal_external or "").strip().casefold())


HESTA_ASSET_CLASS_MAPPINGS: dict[tuple[str, str], AssetClassMappingRule] = {
    _key("Cash"): AssetClassMappingRule("cash", False),
    _key("Cash Total"): AssetClassMappingRule("cash", True),
    _key("Fixed Income"): AssetClassMappingRule("fixed_income", False),
    _key("Fixed Income", "Externally Managed"): AssetClassMappingRule("fixed_income", False),
    _key("Fixed Income", "Internally Managed"): AssetClassMappingRule("fixed_income", False),
    _key("Fixed Income Total"): AssetClassMappingRule("fixed_income", True),
    _key("Listed Equity"): AssetClassMappingRule("listed_equity", False),
    _key("Listed Equity Total"): AssetClassMappingRule("listed_equity", True),
    _key("Listed Infrastructure"): AssetClassMappingRule("listed_infrastructure", False),
    _key("Listed Infrastructure Total"): AssetClassMappingRule("listed_infrastructure", True),
    _key("Listed Property"): AssetClassMappingRule("listed_property", False),
    _key("Listed Property Total"): AssetClassMappingRule("listed_property", True),
    _key("Unlisted Equity", "Internally Managed"): AssetClassMappingRule("unlisted_equity", False),
    _key("Unlisted Equity", "Externally Managed"): AssetClassMappingRule("unlisted_equity", False),
    _key("Unlisted Equity External Total"): AssetClassMappingRule("unlisted_equity", True),
    _key("Unlisted Equity Internal Total"): AssetClassMappingRule("unlisted_equity", True),
    _key("Unlisted Infrastructure", "Internally Managed"): AssetClassMappingRule("unlisted_infrastructure", False),
    _key("Unlisted Infrastructure", "Externally Managed"): AssetClassMappingRule("unlisted_infrastructure", False),
    _key("Unlisted Infrastructure External Total"): AssetClassMappingRule("unlisted_infrastructure", True),
    _key("Unlisted Infrastructure Internal Total"): AssetClassMappingRule("unlisted_infrastructure", True),
    _key("Unlisted Property", "Internally Managed"): AssetClassMappingRule("unlisted_property", False),
    _key("Unlisted Property", "Externally Managed"): AssetClassMappingRule("unlisted_property", False),
    _key("Unlisted Property Total"): AssetClassMappingRule("unlisted_property", True),
}


def lookup_asset_class_mapping(
    asset_class: str,
    internal_external: str | None = None,
) -> AssetClassMappingRule | None:
    direct = HESTA_ASSET_CLASS_MAPPINGS.get(_key(asset_class, internal_external))
    if direct is not None:
        return direct
    if not internal_external:
        return HESTA_ASSET_CLASS_MAPPINGS.get(_key(asset_class))
    return None
