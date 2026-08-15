"""Run M08-03 evaluator scenarios."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from .evaluator import evaluate_all


def main() -> int:
    records = evaluate_all()
    passed = all(record.passed for record in records)
    sys.stdout.write(
        json.dumps(
            {
                "module": "GLIO-PROTEOGEN-M08-03",
                "contract_version": "0.1.0-provisional",
                "scenarios": [asdict(record) for record in records],
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
