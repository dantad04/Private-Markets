# Frozen Host-Plus Adapter Contract

This contract fixture is deliberately built from the real Host-Plus file, not a
synthetic CSV.

The source file is [tests/fixtures/real/Host-PlusHigh Growth.csv](</Users/dantadmore/Documents/Private-Markets/tests/fixtures/real/Host-PlusHigh Growth.csv>).
The extract fixture is
[tests/fixtures/hostplus_real_extract.csv](/Users/dantadmore/Documents/Private-Markets/tests/fixtures/hostplus_real_extract.csv).

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

## Why the extract is the whole file

Unlike UniSuper, this real file already is a single narrow option slice. The
least lossy real extract is therefore the whole file.

## Contract artifact

`canonical_output.json` is the full serialisation of
`HostPlusPhdStateMachineAdapter().parse(...)` over the extract fixture. It is
checked in so contract drift is visible in review.

## Regeneration

```bash
python3 -m scripts.regenerate_hostplus_contract --confirm
```
