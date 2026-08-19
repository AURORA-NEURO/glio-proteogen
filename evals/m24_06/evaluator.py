"""Locked M24-06 robustness and safe-failure scenario matrix."""

from __future__ import annotations

from typing import Any

from glio_proteogen.contracts.m24_06 import ChallengeDisposition, RobustnessStatus
from glio_proteogen.modules.c21_reference_material import (
    m24_06_robustness_ood_challenge as m2406,
)

from .fixture import request

_CHALLENGE_KIND_COUNT = 8


def run_matrix() -> dict[str, Any]:
    service = m2406.M2406Service()
    baseline = request()
    supported = service.evaluate(baseline)
    replay = service.verify_replay(supported)
    unsupported = baseline.scenarios[0].model_copy(
        update={"expected_disposition": ChallengeDisposition.ABSTAIN_UNSUPPORTED}
    )
    unsupported_result = service.evaluate(
        baseline.model_copy(update={"scenarios": (unsupported, *baseline.scenarios[1:])})
    )
    scenarios = {
        "supported": supported.status is RobustnessStatus.EVALUATED,
        "eight_challenge_kinds": supported.robustness_surface is not None
        and len(supported.robustness_surface.observations) == _CHALLENGE_KIND_COUNT,
        "replay_verified": replay.result_digest == supported.result_digest,
        "unsupported_abstained": unsupported_result.status is RobustnessStatus.ABSTAINED,
        "safe_failure_reported": unsupported_result.safe_failure_report is not None
        and unsupported_result.safe_failure_report.abstained,
    }
    return {
        "module": "M24-06",
        "scenario_count": len(scenarios),
        "scenario_ids": list(scenarios),
        "scenarios": scenarios,
        "passed": all(scenarios.values()),
        "supported_result_digest": supported.result_digest,
    }
