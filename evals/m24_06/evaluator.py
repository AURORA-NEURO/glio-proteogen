"""Executable M24-06 scenario and adversarial evaluator."""

from __future__ import annotations

import json
import sys
from typing import Any

from evals.m24_06.fixture import build_request, denied_request, review_request, unsupported_request
from glio_proteogen.contracts.m24_06 import RobustnessStatus
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c21_reference_material.m24_06_robustness_shift_ood_challenge import (
    M2406ReplayError,
    M2406Service,
)

_CHALLENGE_KIND_COUNT = 8


def run_evaluation() -> dict[str, Any]:
    service = M2406Service()
    request = build_request()
    result = service.challenge(request)
    repeat = service.challenge(request)
    unsupported = service.challenge(unsupported_request())
    checks: dict[str, bool] = {
        "evaluated": result.status is RobustnessStatus.EVALUATED,
        "all_eight_challenge_kinds": result.robustness_surface is not None
        and len(result.robustness_surface.observations) == _CHALLENGE_KIND_COUNT,
        "within_envelope": result.robustness_surface is not None
        and all(item.within_envelope for item in result.robustness_surface.observations),
        "upstream_media_boundary": request.upstream_result.media_type
        == "application/vnd.glio-proteogen.m24-05+json",
        "support_domain": result.support_decision.status is SupportStatus.SUPPORTED,
        "deterministic_result": result.result_digest == repeat.result_digest,
        "replay_verified": service.verify_replay(result).result_digest == result.result_digest,
        "review_abstention": service.challenge(review_request()).status
        is RobustnessStatus.ABSTAINED,
        "unsupported_abstention": unsupported.status is RobustnessStatus.ABSTAINED,
        "safe_failure_report": unsupported.safe_failure_report is not None,
        "denied_fail_closed": _denied(service),
        "parent_boundary": result.parent_target == "biomarker panel" and not result.emits_parent,
    }
    try:
        service.verify_replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    except M2406ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "module": "M24-06",
        "checks": checks,
        "fixture_request_digest": result.request_digest,
        "fixture_result_digest": result.result_digest,
        "passed": all(checks.values()),
        "scenario_count": len(checks),
    }


def _denied(service: M2406Service) -> bool:
    try:
        service.challenge(denied_request())
    except ValueError:
        return True
    return False


def main() -> None:
    report = run_evaluation()
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


__all__ = ["run_evaluation"]
