"""Run M08-01 evaluation scenarios and emit JSON."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m08_01.evaluator import evaluate_all


def main() -> int:
    records = evaluate_all()
    payload = {
        "module": "GLIO-PROTEOGEN-M08-01",
        "contract_version": "0.1.0-provisional",
        "scenarios": [asdict(record) for record in records],
        "passed": all(record.passed for record in records),
    }
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
