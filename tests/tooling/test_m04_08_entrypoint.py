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
    names = {item["name"] for item in report["checks"]}
    assert report["genuine_e2e_executed"] is False
    assert report["synthetic_chain_executed"] is True
    assert "scenario.synthetic_m0401_m0407_chain" in names
    assert "scenario.genuine_m0401_m0407_chain" not in names


def test_m04_08_evidence_verifier_enforces_dependency_guard() -> None:
    root = Path(__file__).parents[2]
    completed = subprocess.run(
        [sys.executable, "release-evidence/m04_08/verify.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "dependency_fail_closed": True,
        "evaluation": True,
        "fixture_ceiling": True,
        "module": True,
        "synthetic_only": True,
    }
