"""Run M08-03 evaluator scenarios."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m08_03.evaluator import evaluate_all, evaluate_replay_and_tamper


def main() -> int:
    records = evaluate_all()
    replay_and_tamper = evaluate_replay_and_tamper()
    passed = all(record.passed for record in records) and replay_and_tamper
    sys.stdout.write(
        json.dumps(
            {
                "module": "GLIO-PROTEOGEN-M08-03",
                "contract_version": "0.1.0-provisional",
                "scenarios": [asdict(record) for record in records],
                "replay_and_tamper": replay_and_tamper,
                "passed": passed,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
