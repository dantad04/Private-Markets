from __future__ import annotations

import json
from pathlib import Path


FIXTURE_PATH = Path("tests/fixtures/hesta_synthetic_high_growth_contract.csv").resolve()
EXPECTED_PATH = Path("tests/fixtures/hesta_expected_outputs.json").resolve()


def load_expected_outputs() -> dict[str, object]:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


EXPECTED_TOTAL_ROWS = int(load_expected_outputs()["summary"]["total_rows_emitted"])
