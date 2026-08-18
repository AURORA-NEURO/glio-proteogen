# ruff: noqa: E402, TRY003
"""Refresh replay-bound research evaluator evidence from the current source tree."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.research_proteomics.cohort import run_evaluator as run_cohort_evaluator
from evals.research_proteomics.precursor_policy import run_precursor_policy_evaluator
from evals.research_proteomics.run import run_benchmark, run_evaluator

_EVIDENCE = _ROOT / "docs" / "evidence" / "research-foundation" / "evaluation.json"


def refresh() -> None:
    """Refresh evaluator, cohort, and benchmark projections without changing metadata."""

    evidence = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    evaluation = run_evaluator()
    cohort = run_cohort_evaluator()
    precursor_policy = run_precursor_policy_evaluator()
    if not evaluation["passed"] or not cohort["passed"] or not precursor_policy["passed"]:
        raise ValueError("locked research evaluator did not pass")
    evidence["fixture_sha256"] = evaluation["fixture_sha256"]
    evidence["evaluator"] = evaluation
    evidence["cohort_evaluation"] = cohort
    evidence["precursor_policy_evaluation"] = precursor_policy
    evidence["benchmark"] = run_benchmark(iterations=10)
    _EVIDENCE.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    refresh()
