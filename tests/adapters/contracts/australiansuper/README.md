# Frozen AustralianSuper Adapter Contract

This directory stores the committed canonical parse artifacts for the real
AustralianSuper `Member Direct PHD (1).csv`, `Stable PHD (1).csv`, and
`Conservative PHD (1).csv` fixtures. They freeze the bounded official-file
slices currently approved for loader/admin ingest while the broader
AustralianSuper option family remains under staged mapping review.

The contracts are generated from:

- `tests/fixtures/real/australiansuper/Member Direct PHD (1).csv`
- `tests/fixtures/real/australiansuper/Stable PHD (1).csv`
- `tests/fixtures/real/australiansuper/Conservative PHD (1).csv`
- `AustralianSuperPhdAdapter().parse(...)`

Regenerate only when the underlying fixture or intentionally approved canonical
behaviour changes.

Command:

```bash
python3 -m scripts.regenerate_australiansuper_contract --confirm
```
