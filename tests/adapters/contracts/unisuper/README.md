# Frozen UniSuper Adapter Contract

This contract fixture is deliberately built from a real-file extract, not a
synthetic CSV.

The source file is [tests/fixtures/real/UniSuper.csv](/Users/dantadmore/Documents/Private-Markets/tests/fixtures/real/UniSuper.csv),
which is a 26,890-row, 16-option UniSuper Portfolio Holdings Disclosure file.
The extract fixture is
[tests/fixtures/unisuper_real_extract.csv](/Users/dantadmore/Documents/Private-Markets/tests/fixtures/unisuper_real_extract.csv).

## Extract contents

The extract contains 2 complete options:

1. `Conservative` — 3,885 rows
   This is the rule-heavy option. It contains:
   - cash rows including the multi-currency `BNP PARIBAS SA (AUSTRALIA)` sequence
   - fixed income internal and external sections
   - quoted names with embedded commas such as `AUSTRALIA, COMMONWEALTH OF (GOVERNMENT)`
   - unlisted equity internally managed ownership rows including `IFM INVESTORS PTY LIMITED`, `AMBERSIDE LP`, `PARTNERS GROUP WANGAL LP`, and `APAX EUROPE VI LP`
   - the `INDUSTRY SUPER HOLDINGS PTY LTD 7.5% MINORITY DISCOUNT` name-only case
   - TABLE 2, TABLE 3, and TABLE 4 posture sections that must be excluded
   - all three observed scope-modifier string variants
   - listed and unlisted alternatives section labels that are present in the real file even though the task prompt simplifies them

2. `Cash` — 111 rows
   This keeps the fixture multi-option so the loader/admin path proves that one
   UniSuper source file can populate more than one investment option.

Total extract size: 3,996 rows.

## Why this shape

The task prompt asked for 500-1500 rows, but also required at least one
complete `Conservative` option. In the real file, `Conservative` alone is 3,885
rows, so a complete-option extract cannot satisfy both constraints at once.

This fixture keeps the "complete option from the real file" rule intact and
adds the smallest practical second option for cross-option verification.

## Contract artifact

`canonical_output.json` is the full serialisation of
`UniSuperPhdStateMachineAdapter().parse(...)` over the extract fixture.
`full_source_canonical_output.json` is the full serialisation over the
accepted 2025-12-31 16-option source fixture. Both are checked in so contract
drift is visible in review.

## Regeneration

```bash
python3 -m scripts.regenerate_unisuper_contract --confirm
```
