from __future__ import annotations

from dataclasses import dataclass

from adapters.sunsuper_schema_errors import UnknownAssetClassError
from adapters.sunsuper_schema_identity import AUSTRALIANSUPER_REAL_HEADER


MANAGEMENT_STYLE_VALUES = {"internally managed", "externally managed"}
PORTFOLIO_POSTURE_ASSET_CLASSES = {"derivatives"}


@dataclass(frozen=True)
class AustralianSuperDerivedShape:
    normalised_asset_class_raw: str
    qualifier: str
    canonical_asset_class_code: str
    current_management_style_raw: str | None


def derive_row_shape(
    *,
    row_number: int,
    asset_class_raw: str,
    filter_raw: str,
    sub_filter_raw: str,
) -> AustralianSuperDerivedShape:
    asset_class = asset_class_raw.strip()
    filter_value = filter_raw.strip()
    sub_filter_value = sub_filter_raw.strip()
    current_management_style = _management_style(filter_value, sub_filter_value)

    if asset_class == "Cash":
        return AustralianSuperDerivedShape("Cash", "All Assets", "cash", None)

    if asset_class == "Fixed Income":
        if sub_filter_value == "Fixed Income Private Debt":
            return AustralianSuperDerivedShape(
                "Private Debt",
                "Fixed Income Private Debt",
                "private_debt",
                current_management_style,
            )
        return AustralianSuperDerivedShape(
            "Fixed Income",
            filter_value or "All Assets",
            "fixed_income",
            current_management_style,
        )

    if asset_class == "Equity":
        if filter_value == "Listed":
            return AustralianSuperDerivedShape("Listed Equity", "Listed", "listed_equity", None)
        if filter_value == "Unlisted":
            if sub_filter_value == "Private Equity":
                return AustralianSuperDerivedShape("Private Equity", "Private Equity", "unlisted_equity", None)
            return AustralianSuperDerivedShape(
                "Unlisted Equity",
                sub_filter_value or "Unlisted",
                "unlisted_equity",
                current_management_style,
            )

    if asset_class == "Infrastructure":
        if filter_value == "Listed":
            return AustralianSuperDerivedShape("Listed Infrastructure", "Listed", "listed_infrastructure", None)
        if filter_value == "Unlisted":
            return AustralianSuperDerivedShape(
                "Unlisted Infrastructure",
                sub_filter_value or "Unlisted",
                "unlisted_infrastructure",
                current_management_style,
            )

    if asset_class == "Property":
        if filter_value == "Listed":
            return AustralianSuperDerivedShape("Listed Property", "Listed", "listed_property", None)
        if filter_value == "Unlisted":
            return AustralianSuperDerivedShape(
                "Unlisted Property",
                sub_filter_value or "Unlisted",
                "unlisted_property",
                current_management_style,
            )

    if asset_class == "Alternatives":
        if filter_value == "Listed":
            return AustralianSuperDerivedShape("Listed Alternatives", "Listed", "alternatives", None)
        if filter_value == "Unlisted":
            return AustralianSuperDerivedShape(
                "Unlisted Alternatives",
                sub_filter_value or "Unlisted",
                "alternatives",
                current_management_style,
            )

    raise UnknownAssetClassError(
        row_number,
        asset_class_raw,
        f"{filter_raw!r} / {sub_filter_raw!r}",
    )


def _management_style(filter_raw: str, sub_filter_raw: str) -> str | None:
    for value in (sub_filter_raw, filter_raw):
        if value.strip().casefold() in MANAGEMENT_STYLE_VALUES:
            return value.strip()
    return None
