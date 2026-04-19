# Frozen AustralianSuper Adapter Contract

This directory stores the committed canonical parse artifact for the real
AustralianSuper `Member Direct PHD (1).csv` fixture. It freezes the bounded
official-file slice currently approved for loader/admin ingest while the broader
AustralianSuper option family remains under staged mapping review.

The contract is generated from:

- `tests/fixtures/real/australiansuper/Member Direct PHD (1).csv`
- `AustralianSuperPhdAdapter().parse(...)`

Regenerate only when the underlying fixture or intentionally approved canonical
behaviour changes.

Command:

```bash
python3 -m scripts.regenerate_australiansuper_contract --confirm
```
