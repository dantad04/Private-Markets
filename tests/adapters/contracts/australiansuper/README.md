# Frozen AustralianSuper Adapter Contract

This directory stores the committed canonical parse artifacts for the real
AustralianSuper `Member Direct PHD (1).csv`, `Stable PHD (1).csv`,
`Conservative PHD (1).csv`, `Balanced PHD (6).csv`, and
`High Growth PHD (2).csv`, `Cash PHD (1).csv`,
`Diversified Fixed Interest PHD (1).csv`,
`Indexed Diversified PHD (1).csv`, `International Shares PHD.csv`, and
`Socially Aware PHD.csv` fixtures. They freeze the bounded official-file
slices currently approved for loader/admin ingest while unsupplied
AustralianSuper options remain out of scope.

The contracts are generated from:

- `tests/fixtures/real/australiansuper/Member Direct PHD (1).csv`
- `tests/fixtures/real/australiansuper/Stable PHD (1).csv`
- `tests/fixtures/real/australiansuper/Conservative PHD (1).csv`
- `tests/fixtures/real/australiansuper/Balanced PHD (6).csv`
- `tests/fixtures/real/australiansuper/High Growth PHD (2).csv`
- `tests/fixtures/real/australiansuper/Cash PHD (1).csv`
- `tests/fixtures/real/australiansuper/Diversified Fixed Interest PHD (1).csv`
- `tests/fixtures/real/australiansuper/Indexed Diversified PHD (1).csv`
- `tests/fixtures/real/australiansuper/International Shares PHD.csv`
- `tests/fixtures/real/australiansuper/Socially Aware PHD.csv`
- `AustralianSuperPhdAdapter().parse(...)`

Regenerate only when the underlying fixture or intentionally approved canonical
behaviour changes.

Command:

```bash
python3 -m scripts.regenerate_australiansuper_contract --confirm
```
