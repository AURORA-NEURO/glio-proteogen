"""Executable M24-04 external transport evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m24_04 import (
    EvaluationStatus,
    TransportDimension,
    TransportStatus,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m24_04_external_transport_evaluator import (
    M2404AuthorizationError,
    M2404ReplayError,
    M2404Service,
)

from .fixture import build_request, denied_request, narrowed_request, not_evaluable_request


def run_evaluator() -> dict[str, Any]:
    service = M2404Service()
    request = build_request()
    result = service.generate(request)
    repeated = service.generate(request)
    checks: dict[str, bool] = {
        "evaluated": result.status is EvaluationStatus.EVALUATED,
        "all_dimensions": (
            result.report is not None
            and {item.dimension for item in result.report.evaluations} == set(TransportDimension)
        ),
        "independent_validations": (
            result.report is not None
            and len(result.report.validations) == len(tuple(TransportDimension))
        ),
        "support_domain": (
            result.report is not None
            and result.report.support_domain.status is TransportStatus.SUPPORTED
        ),
        "deterministic_result": result.result_digest == repeated.result_digest,
        "replay_verified": service.replay(result).result_digest == result.result_digest,
        "parent_boundary": (
            result.emits_parent is False and result.parent_target == "biomarker panel"
        ),
        "human_review_required": result.human_review_required is True,
    }
    narrowed = service.generate(narrowed_request())
    checks["domain_narrowing_abstention"] = (
        narrowed.status is EvaluationStatus.ABSTAINED
        and narrowed.report is None
        and narrowed.human_review_required
    )
    missing = service.generate(not_evaluable_request())
    checks["not_evaluable_abstention"] = (
        missing.status is EvaluationStatus.ABSTAINED
        and missing.report is None
        and missing.support_decision.status.value == "review_required"
    )
    try:
        service.generate(denied_request())
    except M2404AuthorizationError:
        checks["denied_fail_closed"] = True
    else:
        checks["denied_fail_closed"] = False
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.replay(tampered)
    except M2404ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "module": "M24-04",
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
