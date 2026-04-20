# AustralianSuper Socially Aware Go / No-Go Note

Date: 2026-04-20

## Recommendation

No-go for approval in this pass.

`Socially Aware PHD.csv` should remain review-gated for now. The real file is
clean enough to parse on the existing thin `AustralianSuperPhdAdapter`, but the
evidence is not strong enough yet to promote it onto the approved production
path alongside `Member Direct`, `Stable`, and `Conservative Balanced`.

## Real-file evidence

1. Schema fingerprint differs from the approved `Stable` / `Conservative`
   shape.
   `Socially Aware` fingerprint: `ce02cfbf2d7a1988f1cca2adc7635e0f5914c644e027e1da660824d6922bcaba`
   Approved `Stable` / `Conservative` fingerprint:
   `9155b44a6c15c0e694f43fef3402dc4840c3937803c8606f27318c5699afb413`
2. Taxonomy keys do not introduce a new mapping problem, but they are only a
   narrower subset of the approved path.
   The real `Socially Aware` file produced no taxonomy keys outside the current
   approved `Stable` / `Conservative` path, but it is missing 20 of those
   approved keys because the slice does not contain the broader private-asset
   families exercised by `Stable` and `Conservative Balanced`.
3. Duplicate-view merge behaviour is not positively exercised in the real
   `Socially Aware` file.
   `merged_duplicate_groups = 0`
   `metadata_attached_rows = 0`
   That means the real file does not prove the metadata-attachment path that
   was central to approving `Stable` and `Conservative Balanced`.
4. Derivative / posture exclusion is still exercised.
   `skipped_portfolio_posture_rows = 15`
   So the file does hit the derivative-posture exclusion rule and remains
   compatible with the existing thin wrapper.
5. Ambiguity review remains active.
   `ambiguous_duplicate_groups = 44`
   The file still emits review events for same-name value rows across asset
   classes, so approving it would need to be an explicit governance choice, not
   an assumption that the slice is trivial.

## Why this stays gated

The current evidence is mostly negative or subset-shaped:

1. No new taxonomy keys were found.
2. No new parser rules were required.
3. But the real file also does not prove the duplicate-view merge path on an
   official `Socially Aware` sample, because there were no actual metadata
   attachments to validate.

That makes this a weak approval case if the goal is disciplined real-file
promotion rather than speculative bundling.

## Safe next step

If `Socially Aware` is revisited, the next pass should stay bounded:

1. Decide whether a narrower no-merge slice is acceptable for approval on its
   own exact seed.
2. If yes, add a dedicated `Socially Aware` seed on the existing thin wrapper
   path with exact option-code / option-name expectations.
3. If no, keep it gated until another real `Socially Aware` file or period
   provides positive merge-path evidence.
