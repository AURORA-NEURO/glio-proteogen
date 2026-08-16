"""Executable M25-03 evaluator matrix."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final

from glio_proteogen.contracts.m25_03 import (
    BenchmarkStatus,
    ValidationStatus,
    canonical_request_digest,
)
from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation import (
    BenchmarkSubmission,
    M2503Plugin,
    M2503Service,
)

from .fixture import build_request, denied_request

EVALUATOR_VERSION: Final = "m25-03-evaluator-v1"


@dataclass(frozen=True, slots=True)
class EvaluationCheck:
    """One named executable evaluator assertion."""

    name: str
    passed: bool
    detail: str


def evaluate() -> tuple[EvaluationCheck, ...]:
    """Run the locked M25-03 scenario matrix."""

    service = M2503Service()
    request = build_request()
    completed = service.execute(request)
    repeated = service.execute(request)
    checks: list[EvaluationCheck] = [
        EvaluationCheck(
            "completed_benchmark_dossier",
            completed.status is BenchmarkStatus.COMPLETED and completed.dossier is not None,
            f"status={completed.status.value};dossier={completed.dossier is not None}",
        ),
        EvaluationCheck(
            "non_passing_metric_abstention",
            service.execute(build_request(metric_status=ValidationStatus.FAIL)).status
            is BenchmarkStatus.ABSTAINED,
            "failed baseline metric remains an explicit abstention",
        ),
        EvaluationCheck(
            "non_passing_ablation_abstention",
            service.execute(build_request(ablation_status=ValidationStatus.NOT_EVALUABLE)).status
            is BenchmarkStatus.ABSTAINED,
            "non-evaluable ablation remains an explicit abstention",
        ),
        EvaluationCheck(
            "non_passing_compute_match_abstention",
            service.execute(build_request(comparison_status=ValidationStatus.FAIL)).status
            is BenchmarkStatus.ABSTAINED,
            "failed compute match remains an explicit abstention",
        ),
        EvaluationCheck(
            "deterministic_reexecution",
            completed.model_dump(mode="json") == repeated.model_dump(mode="json"),
            "identical canonical result across repeated calls",
        ),
        EvaluationCheck(
            "replay_verification",
            service.verify_replay(completed).model_dump(mode="json")
            == completed.model_dump(mode="json"),
            "canonical result replay is exact",
        ),
        EvaluationCheck(
            "plugin_parity",
            M2503Plugin(service)
            .run(M2503Plugin(service).validate(BenchmarkSubmission(request)))
            .model_dump(mode="json")
            == completed.model_dump(mode="json"),
            "strict plugin result equals service result",
        ),
        EvaluationCheck(
            "fixture_request_digest_locked",
            canonical_request_digest(request) == canonical_request_digest(build_request()),
            canonical_request_digest(request),
        ),
    ]
    try:
        service.execute(denied_request())
    except ValueError:
        denied_passed = True
    else:
        denied_passed = False
    checks.append(
        EvaluationCheck(
            "denied_control_rejected",
            denied_passed,
            "support denial fails closed before benchmark execution",
        )
    )
    return tuple(checks)


def main() -> int:
    """Print a compact evaluator report and return a process status."""

    checks = evaluate()
    for check in checks:
        sys.stdout.write(f"{check.name}: {'PASS' if check.passed else 'FAIL'} ({check.detail})\n")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EVALUATOR_VERSION", "EvaluationCheck", "evaluate", "main"]
