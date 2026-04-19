# Frozen ART-Sunsuper Adapter Contract

This directory holds the frozen adapter-contract artifact for the synthetic
ART-Sunsuper fixture that exercises the shared Sunsuper schema and duplicate-view
metadata attachment.

`canonical_output.json` is the full canonical serialisation of the current
`ArtSunsuperPhdAdapter().parse(...)` output for the checked-in synthetic fixture.
It includes:

1. Every `SourceNormalisedHoldingRecord` field for all emitted rows.
2. `structural_metadata`
3. `parse_statistics`
4. `schema_fingerprint`
5. `adapter_warnings`

The file is checked into the repo so a reviewer can diff exact contract drift in
a pull request. The fixture is synthetic on purpose: raw source files do not
belong in git.

## Regeneration

Regeneration is intentional and manual. Run this from the repo root:

```bash
python3 -m scripts.regenerate_art_sunsuper_contract --confirm
```

The script prints a warning before rewriting the artifact. It will not write
anything unless `--confirm` is present.
