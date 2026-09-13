# ruff: noqa: E402, TRY003
"""Refresh replay-bound research evaluator evidence from the current source tree."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.research_proteomics.cohort import run_evaluator as run_cohort_evaluator
from evals.research_proteomics.fdr_quant_group_invariants import (
    run_fdr_quant_group_invariants_evaluator,
)
from evals.research_proteomics.mzidentml_provenance import (
    run_mzidentml_provenance_evaluator,
)
from evals.research_proteomics.precursor_policy import run_precursor_policy_evaluator
from evals.research_proteomics.run import run_benchmark, run_evaluator

_EVIDENCE = _ROOT / "docs" / "evidence" / "research-foundation" / "evaluation.json"


def refresh(*, output: Path = _EVIDENCE, template: Path = _EVIDENCE) -> None:
    """Refresh projections from a template into an explicitly selected output."""

    evidence = json.loads(template.read_text(encoding="utf-8"))
    evaluation = run_evaluator()
    cohort = run_cohort_evaluator()
    precursor_policy = run_precursor_policy_evaluator()
    mzidentml_provenance = run_mzidentml_provenance_evaluator()
    fdr_quant_group_invariants = run_fdr_quant_group_invariants_evaluator()
    if (
        not evaluation["passed"]
        or not cohort["passed"]
        or not precursor_policy["passed"]
        or not mzidentml_provenance["passed"]
        or not fdr_quant_group_invariants["passed"]
    ):
        raise ValueError("locked research evaluator did not pass")
    evaluation["scenario_ids"] = [
        outcome["scenario_id"]
        for outcome in cast("list[object]", evaluation["outcomes"])
        if isinstance(outcome, dict) and "scenario_id" in outcome
    ]
    cohort["scenario_ids"] = [
        outcome["id"]
        for outcome in cast("list[object]", cohort["outcomes"])
        if isinstance(outcome, dict) and "id" in outcome
    ]
    evidence["fixture_sha256"] = evaluation["fixture_sha256"]
    evidence["evaluation"] = evaluation
    evidence["evaluator"] = evaluation
    evidence["cohort_evaluation"] = cohort
    evidence["precursor_policy_evaluation"] = precursor_policy
    evidence["mzidentml_provenance_evaluation"] = mzidentml_provenance
    evidence["fdr_quant_group_invariants_evaluation"] = fdr_quant_group_invariants
    evidence["benchmark"] = run_benchmark(iterations=10)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main(arguments: Sequence[str] | None = None) -> int:
    """Emit complete current evaluator evidence without requiring checkout mutation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=_EVIDENCE)
    parser.add_argument("--template", type=Path, default=_EVIDENCE)
    parsed = parser.parse_args(arguments)
    refresh(output=parsed.output, template=parsed.template)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
