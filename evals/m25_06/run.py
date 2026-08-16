"""Run and serialize the M25-06 evaluator matrix."""

from __future__ import annotations

import json

from .evaluator import run_evaluation


def main() -> None:
    print(json.dumps(run_evaluation(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
