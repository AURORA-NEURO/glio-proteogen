"""Regression coverage for the documented M04-08 evaluator entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

EXPECTED_CASE_COUNT = 12


def test_m04_08_evaluator_runs_by_repository_relative_path() -> None:
    root = Path(__file__).parents[2]
    completed = subprocess.run(
        [sys.executable, "evals/m04_08/run.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["module_id"] == "GLIO-PROTEOGEN-M04-08"
    assert report["declared_case_count"] == report["executed_check_count"] == EXPECTED_CASE_COUNT
    assert report["passed"] is True
