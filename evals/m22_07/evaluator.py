"""Executable M22-07 evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m22_07 import OperationalDimension
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material import (
    m22_07_human_factors_operational_evaluator as m2207,
)

from .fixture import build_request, denied_request, failed_request, unsupported_request


def run_evaluator() -> dict[str, Any]:
    service = m2207.M2207Service()
    request = build_request()
    result = service.evaluate(request)
    repeated = service.evaluate(request)
    abstained = service.evaluate(unsupported_request())
    failed = service.evaluate(failed_request())
    checks: dict[str, bool] = {
        "evaluated": result.status.value == "evaluated",
        "report_present": result.report is not None,
        "all_required_dimensions": (
            result.report is not None
            and set(result.report.configuration.required_dimensions) == set(OperationalDimension)
        ),
        "deterministic_result": result.result_digest == repeated.result_digest,
        "replay_verified": service.replay(result).result_digest == result.result_digest,
        "explicit_abstention": abstained.status.value == "abstained"
        and abstained.report is None
        and abstained.human_review_required,
        "failed_metric_visible": failed.status.value == "evaluated"
        and failed.report is not None
        and bool(failed.findings),
        "parent_boundary": result.emits_parent is False
        and result.parent_target == "protein-RNA discordance",
    }
    try:
        service.evaluate(denied_request())
    except m2207.M2207AuthorizationError:
        checks["denied_fail_closed"] = True
    else:
        checks["denied_fail_closed"] = False
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    try:
        service.replay(tampered)
    except m2207.M2207ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "module": "M22-07",
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
