"""Verify M07-08 evaluator and benchmark evidence before release packaging."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from evals.m07_08.benchmark import run_benchmark  # noqa: E402
from evals.m07_08.run import evaluate  # noqa: E402

MODULE_ID: Final = "GLIO-PROTEOGEN-M07-08"
AUTHORITY_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES: Final = "2504-2547"


def verify(iterations: int = 10) -> dict[str, object]:
    """Return a deterministic evidence summary and fail if either gate is red."""

    evaluation = evaluate()
    benchmark = run_benchmark(iterations)
    passed = evaluation["passed"] is True and benchmark["passed"] is True
    return {
        "module_id": MODULE_ID,
        "authority_sha256": AUTHORITY_SHA256,
        "authority_lines": AUTHORITY_LINES,
        "evaluation": evaluation,
        "benchmark": benchmark,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = verify(arguments.iterations)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "verify"]
