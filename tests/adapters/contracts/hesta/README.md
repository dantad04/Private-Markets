# Frozen Hesta Adapter Contract

This directory holds the Stage 1 frozen adapter-contract artifact for the Hesta fixture.

`canonical_output.json` is the full canonical serialisation of the current `HestaPhdAdapter().parse(...)` output for the checked-in synthetic Hesta fixture. It includes:

1. Every `SourceNormalisedHoldingRecord` field for all 2,835 emitted rows.
2. `structural_metadata`
3. `parse_statistics`
4. `schema_fingerprint`
5. `adapter_warnings`

The file is checked into the repo so a reviewer can diff the exact contract drift in a pull request. This is stricter than inline assertions because it freezes the whole adapter output, not just selected examples. The fixture itself is synthetic on purpose: raw source files do not belong in git.

## Regeneration

Regeneration is intentional and manual. Run this from the repo root:

```bash
python3 -m scripts.regenerate_hesta_contract --confirm
```

The script prints a warning before rewriting the artifact. It will not write anything unless `--confirm` is present.

## Approval Workflow

1. Run the regeneration command only when a contract change is intended.
2. Review the diff in `canonical_output.json`.
3. Commit the change with an explicit message explaining why the Stage 1 contract changed.
4. In any PR that changes `canonical_output.json`, call out clearly that the drift is intentional and explain the reason.
