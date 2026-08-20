"""Direct-file execution regressions for research evaluator scripts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = (
    "fdr_quant_group_invariants.py",
    "mzidentml_provenance.py",
    "precursor_policy.py",
    "quantification_policy.py",
)


@pytest.mark.parametrize("script_name", _SCRIPTS)
def test_research_evaluator_file_entrypoint_is_executable(script_name: str) -> None:
    """Each research evaluator emits a passing JSON result when launched by path."""

    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(_ROOT / "evals" / "research_proteomics" / script_name)],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["passed"] is True
