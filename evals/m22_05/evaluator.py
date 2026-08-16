"""Executable M22-05 evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m22_05 import SubgroupDimension
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m22_05_subgroup_equity_evaluator import (
    M2205AuthorizationError,
    M2205ReplayError,
    M2205Service,
)

from .fixture import build_request, denied_request, unsupported_request


def run_evaluator() -> dict[str, Any]:
    service = M2205Service()
    request = build_request()
    result = service.evaluate(request)
    repeated = service.evaluate(request)
    abstained = service.evaluate(unsupported_request())
    checks: dict[str, bool] = {
        "evaluated": result.status.value == "evaluated",
        "report_present": result.report is not None,
        "all_required_dimensions": (
            result.report is not None
            and set(result.report.configuration.required_dimensions)
            == set(SubgroupDimension)
        ),
        "deterministic_result": result.result_digest == repeated.result_digest,
        "replay_verified": service.replay(result).result_digest == result.result_digest,
        "explicit_abstention": abstained.status.value == "abstained"
        and abstained.report is None
        and abstained.human_review_required,
        "parent_boundary": result.emits_parent is False
        and result.parent_target == "protein-RNA discordance",
    }
    try:
        service.evaluate(denied_request())
    except M2205AuthorizationError:
        checks["denied_fail_closed"] = True
    else:
        checks["denied_fail_closed"] = False
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.replay(tampered)
    except M2205ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "module": "M22-05",
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
