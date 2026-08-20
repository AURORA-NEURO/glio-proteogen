"""Executable M22-03 evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m22_03_internal_benchmark_ablation import (
    M2203AuthorizationError,
    M2203ReplayError,
    M2203Service,
)

from .fixture import build_request, denied_request


def run_evaluator() -> dict[str, Any]:
    service = M2203Service()
    request = build_request()
    result = service.generate(request)
    repeated = service.generate(request)
    nested_evidence_digests = (
        {item.reference.digest for item in request.split.evidence}
        | {
            item.reference.digest
            for baseline in request.baseline_runs
            for item in baseline.evidence
        }
        | {
            item.reference.digest
            for baseline in request.baseline_runs
            for metric in baseline.metrics
            for item in metric.evidence
        }
        | {item.reference.digest for ablation in request.ablations for item in ablation.evidence}
        | {
            item.reference.digest
            for comparison in request.comparisons
            for item in comparison.evidence
        }
    )
    checks: dict[str, bool] = {
        "completed": result.status.value == "completed",
        "locked_split": result.dossier is not None and result.dossier.split.locked,
        "simple_and_mature": (
            result.dossier is not None
            and {baseline.kind.value for baseline in result.dossier.baselines}
            == {"simple", "mature"}
        ),
        "ablation_visible": result.dossier is not None and len(result.dossier.ablations) == 1,
        "compute_matched": result.dossier is not None
        and all(
            comparison.reference_compute_units == comparison.candidate_compute_units
            for comparison in result.dossier.comparisons
        ),
        "deterministic_result": result.result_digest == repeated.result_digest,
        "replay_verified": service.replay(result).result_digest == result.result_digest,
        "provenance_covers_nested_evidence": nested_evidence_digests
        <= set(result.provenance.input_digests),
        "parent_boundary": result.emits_parent is False
        and result.parent_target == "protein-RNA discordance",
    }
    try:
        service.generate(denied_request())
    except M2203AuthorizationError:
        checks["denied_fail_closed"] = True
    else:
        checks["denied_fail_closed"] = False
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.replay(tampered)
    except M2203ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "module": "M22-03",
        "checks": checks,
        "fixture_request_digest": sha256_digest(request),
        "fixture_result_digest": result.result_digest,
        "passed": sum(checks.values()),
        "scenario_count": len(checks),
    }


def main() -> None:
    print(json.dumps(run_evaluator(), sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()
