"""Repository benchmark entry point for M09-07."""

from __future__ import annotations

import json
from dataclasses import asdict

from evals.m09_07.benchmark import run_benchmark

if __name__ == "__main__":
    print(json.dumps(asdict(run_benchmark()), indent=2, sort_keys=True))  # noqa: T201
