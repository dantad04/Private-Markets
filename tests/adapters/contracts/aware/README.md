# Frozen Aware Adapter Contract

This directory holds the frozen adapter-contract artifacts for the synthetic Aware fixture and the accepted
latest-period Aware Investment Funds fixture batch.

Each `*_canonical_output.json` file is the full canonical serialisation of the current `AwarePhdAdapter().parse(...)`
output for one checked-in fixture. It includes:

1. Every `SourceNormalisedHoldingRecord` field for all emitted rows.
2. `structural_metadata`
3. `parse_statistics`
4. `schema_fingerprint`
5. `adapter_warnings`

The files are checked into the repo so a reviewer can diff exact contract drift in a pull request. This is stricter
than inline assertions because it freezes the whole adapter output, not just selected examples.

`canonical_output.json` remains the synthetic vertical-slice contract. The latest-period Investment Funds contracts
are generated from the accepted 2025-12-31 fixture files under
`tests/fixtures/real/aware/`.

## Regeneration

Regeneration is intentional and manual. Run this from the repo root:

```bash
python3 -m scripts.regenerate_aware_contract --confirm
```

The script prints a warning before rewriting the artifact. It will not write anything unless `--confirm` is present.

## Approval Workflow

1. Run the regeneration command only when a contract change is intended.
2. Review the diff in the affected `*_canonical_output.json` files.
3. Commit the change with an explicit message explaining why the Aware contract changed.
4. In any PR that changes `canonical_output.json`, call out clearly that the drift is intentional and explain the reason.
