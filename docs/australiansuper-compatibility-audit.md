# AustralianSuper Compatibility Audit

Date: 2026-04-19

Implementation status update:

- The audit conclusion still stands: real AustralianSuper files are not
  compatible with the ART-Sunsuper adapter as-is.
- The follow-on implementation now exists as a thin `AustralianSuperPhdAdapter`
  with explicit identity verification.
- The approved loader/admin production slice is currently the official
  `Member Direct PHD (1).csv` family. Broader AustralianSuper option shapes
  remain staged behind additional mapping approval.

## Scope

This note records the bounded audit requested after confirming real AustralianSuper
PHD files from the official site were available locally.

Files profiled:

1. `tests/fixtures/real/australiansuper/Stable PHD (1).csv`
2. `tests/fixtures/real/australiansuper/Conservative PHD (1).csv`
3. `tests/fixtures/real/australiansuper/Socially Aware PHD.csv`
4. `tests/fixtures/real/australiansuper/Member Direct PHD (1).csv`

## Verdict

AustralianSuper is **not** compatible with the current ART-Sunsuper /
`SunsuperSchemaPhdAdapter` contract as-is.

It does appear compatible with the same **underlying duplicate-view merge logic**
once a thin fund-specific wrapper normalises the raw CSV into the internal shared
contract.

Recommended end-state for the next bounded step:

1. A thin `AustralianSuperPhdAdapter` or closely related sibling adapter.
2. Reuse the proven duplicate-view merge logic only after header/field
   normalisation.
3. Add identity verification based on source/domain/content signals, not
   `AR**` prefixes.

## Real-file differences from the current ART-Sunsuper contract

1. Header labels and column order differ.
   Current internal contract uses `OptionCode`, `AssetClass`, `WeightingPct`,
   `CurrentManagementStyle`, `IssuerName`, `ManagerName`, `Country`, `Notes`,
   `SourceView`.
   Real AustralianSuper files use `Option Code`, `Asset Class`, `Weighting (%)`,
   `Sub-Filter`, `Issuer Type`, `Actual Currency Exposure (%)`,
   `Actual Asset Allocation (%)`, `Effect of Derivatives Exposure (%)`,
   `Sort Order`.
2. Management view is split across `Filter` and `Sub-Filter`.
   Example: IFM Investors in `Stable PHD (1).csv` row 3420 is `Filter=Unlisted`
   plus `Sub-Filter=Externally Managed`, while the metadata row at 3999 is
   `Filter=Unlisted` plus `Sub-Filter=All Assets`.
3. Aggregate rows are present as ordinary records.
   Real files contain `Name Type = Total` rows that the current ART slice never
   exercised.
4. Derivative posture rows are expressed differently.
   Real files use `Asset Class = Derivatives` together with `Filter = By Asset Class`,
   `By Currency`, and `By Kind`, rather than a single `Derivatives` filter token.
5. Ownership semantics differ.
   The ART narrow slice uses bare decimals already in canonical fraction form
   (`0.18` means 18%). The AustralianSuper real files show numeric percentage
   points such as `1.09` and `2.88`, which need divide-by-100 normalisation.
6. Weighting appears to use numeric percentage points as well.
   Example: `Stable PHD (1).csv` row 2 has `Weighting (%) = 1.41`.
7. Asset-class labelling is broader in the real files.
   Real rows use families such as `Equity`, `Infrastructure`, `Property`,
   `Alternatives`, and rely on `Filter` / `Sub-Filter` to determine listed versus
   unlisted and private-debt/private-equity slices.
8. Metadata coverage is option-dependent.
   `Stable` / `Conservative Balanced` carry `Classification`, `Value Range`, and
   geo-coordinates on unlisted property/infrastructure metadata rows, while
   `Member Direct` has none of those fields populated in the audited file.

## Compatibility evidence

Evidence that the current adapter is **not** compatible as-is:

1. The real header is still 24 columns, but it does not match the current
   `EXPECTED_HEADER`, so the current shared adapter raises `HeaderMismatchError`.
2. The current ART-specific parser assumptions around management filters,
   derivative posture rows, and ownership/weighting semantics are not valid for
   the real AustralianSuper files.

Evidence that the underlying merge logic is still reusable:

1. The real files preserve the same precise-row versus metadata-row pattern for
   unlisted manager exposures.
2. In `Stable PHD (1).csv`, `IFM Investors` row 3420 carries the precise value
   and row 3999 carries the metadata-only `Value Range`, which matches the
   duplicate-view attachment rule already proven in the ART slice.

## Identity checks

The audit retires the old `AR** => ART` shortcut.

Safer signals:

1. Registered fund id and source URL/domain.
2. Branded path tokens such as `australiansuper` or
   `australian-retirement-trust`.
3. Content signals such as AustralianSuper-specific option names
   (`Socially Aware`, `Member Direct`, `Conservative Balanced`).

Non-signal:

1. `AR**` option codes on their own. They are shared-family markers, not fund
   identity.
