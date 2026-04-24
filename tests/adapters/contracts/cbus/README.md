# Cbus Adapter Contracts

This directory stores full canonical serialisations of the current
`CbusPhdAdapter().parse(...)` output for the approved real Cbus fixtures.

The contracts are generated from:

- `tests/fixtures/real/cbus/super-high-growth__1_.csv`
- `tests/fixtures/real/cbus/super-property__1_.csv`
- `tests/fixtures/real/cbus/super-overseas-shares.csv`
- `tests/fixtures/real/cbus/super-australian-shares__1_.csv`
- `tests/fixtures/real/cbus/super-cash.csv`

They freeze the approved 31 December 2025 slices: Table 1 holdings are emitted,
derivative/posture tables are skipped, section labels drive name-column
selection, and row-level disclosure completeness is preserved.

The original High Growth `canonical_output.json` remains the accepted Stage 2
late-add contract. The command below regenerates the later Cbus batch contract
files only.

Command:

```bash
python3 -m scripts.regenerate_cbus_contract --confirm
```
