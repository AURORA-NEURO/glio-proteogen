"""Executable M07-05 hard/soft constraint scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c07_copy_number_dosage.test_m07_05_constraint import _request

from glio_proteogen.modules.c07_copy_number_dosage.m07_05_mechanism_constraint_integrator import (
    M0705ConstraintEngine,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    contract_version: str
    integrated_status: str
    hard_violation_status: str
    missing_feature_status: str
    estimate_count: int
    evaluation_count: int
    ablation_count: int
    replay_verified: bool
    deterministic: bool
    passed: bool


def evaluate() -> EvaluationReport:
    engine = M0705ConstraintEngine()
    first = engine.integrate(_request())
    second = engine.integrate(_request())
    hard_violation = engine.integrate(_request(force_hard_violation=True))
    request = _request()
    missing_constraint = request.constraint_set.constraints[0].model_copy(
        update={"feature_ids": ("feature.missing",)}
    )
    missing_set = request.constraint_set.model_copy(
        update={"constraints": (missing_constraint, request.constraint_set.constraints[1])}
    )
    missing = engine.integrate(request.model_copy(update={"constraint_set": missing_set}))
    replay = engine.verify(first.result, first.canonical_bytes)
    return EvaluationReport(
        module_id="GLIO-PROTEOGEN-M07-05",
        contract_version="0.1.0-provisional",
        integrated_status=first.result.status.value,
        hard_violation_status=hard_violation.result.status.value,
        missing_feature_status=missing.result.status.value,
        estimate_count=len(first.result.estimates),
        evaluation_count=len(first.result.evaluations),
        ablation_count=len(first.result.ablations),
        replay_verified=replay.verified,
        deterministic=first.canonical_bytes == second.canonical_bytes,
        passed=(
            first.result.status.value == "integrated"
            and hard_violation.result.status.value == "abstained"
            and missing.result.status.value == "abstained"
            and bool(first.result.estimates)
            and bool(first.result.ablations)
            and replay.verified
            and first.canonical_bytes == second.canonical_bytes
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = evaluate()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EvaluationReport", "evaluate", "main"]
