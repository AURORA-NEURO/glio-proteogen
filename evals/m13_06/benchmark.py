"""Representative M13-06 bounded replay benchmark."""

from __future__ import annotations

import json
import sys
import timeit
from pathlib import Path

from evals.m13_06.run import _request
from glio_proteogen.modules.c13_proteotype.m13_06_perturbation_sensitivity import (
    simulate_proteotype_perturbation_sensitivity,
)


def main() -> None:
    corpus = json.loads(
        (Path(__file__).parents[2] / "tests" / "fixtures" / "m13_06" / "scenarios.json").read_text()
    )
    case = next(item for item in corpus["cases"] if item["expected"] == "simulated")
    request = _request(case)
    elapsed = timeit.repeat(
        lambda: simulate_proteotype_perturbation_sensitivity(request),
        repeat=5,
        number=20,
    )
    sys.stdout.write(
        json.dumps(
            {
                "module_id": corpus["module_id"],
                "iterations": 100,
                "best_seconds": min(elapsed),
                "mean_seconds": sum(elapsed) / len(elapsed),
                "scope": "public bounded replay operation only",
            },
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
