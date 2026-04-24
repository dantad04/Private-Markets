# Frozen Host-Plus Adapter Contracts

These contract fixtures are deliberately built from real Hostplus files, not
synthetic CSVs.

The source file is [tests/fixtures/real/Host-PlusHigh Growth.csv](</Users/dantadmore/Documents/Private-Markets/tests/fixtures/real/Host-PlusHigh Growth.csv>).
The extract fixture is
[tests/fixtures/hostplus_real_extract.csv](/Users/dantadmore/Documents/Private-Markets/tests/fixtures/hostplus_real_extract.csv).
The latest-period batch fixtures are in
[tests/fixtures/real/hostplus](/Users/dantadmore/Documents/Private-Markets/tests/fixtures/real/hostplus).

## Extract contents

The extract is the full single-option file:

1. `HC High Growth - Class A Option` — 3,264 rows
   This one option exercises the narrow Host-Plus vertical slice:
   - the content markers `HOSTPLUS`, `Table 1 - Assets`, and the portfolio holdings title
   - UTF-8 replacement-character tolerance on the corrupted `Table 2` / `Table 4` lines
   - cash rows with one canonical row per currency for `Citigroup Inc`
   - listed-equity rows with `Security Identifier` and `Units held`
   - unlisted-equity internally managed ownership rows including `Myriota Pty Ltd` and `Industry Super Holdings`
   - unlisted-equity externally managed rows including `IFM Investors Pty Ltd`
   - `Total` section totals plus `Total Investment Items`
   - `Table 2`, `Table 3`, and `Table 4` posture sections that must be excluded

The latest-period mapping-only batch fixtures cover:

1. `HC Australian Shares - Class A Option`
2. `HC Australian Shares - Indexed - Class A Option`
3. `HC Cash - Class A Option`
4. `HC Indexed High Growth - Class A Option`
5. `HC International Shares - Class A Option`
6. `HC SRI High Growth - Class A Option`

These files intentionally exercise only the existing Hostplus Table 1
`Cash`, `Listed Equity`, and `Unlisted Equity` path. Fixed Income,
Unlisted Property, and Unlisted Infrastructure sections remain out of scope for
this contract batch.

## Why the extract is the whole file

Unlike UniSuper, this real file already is a single narrow option slice. The
least lossy real extract is therefore the whole file.

## Contract artifact

Each JSON file is the full serialisation of
`HostPlusPhdStateMachineAdapter().parse(...)` over one real fixture. They are
checked in so contract drift is visible in review.

## Regeneration

```bash
python3 -m scripts.regenerate_hostplus_contract --confirm
```
