"""Executable M25-06 evaluator matrix with deterministic assertions."""

from __future__ import annotations

from typing import Any

from glio_proteogen.contracts.m25_06 import ChallengeDisposition, RobustnessStatus
from glio_proteogen.modules.c21_reference_material.m25_06_robustness_shift_ood_challenge import (
    M2506RobustnessEngine,
)

from .fixture import build_request

_CHALLENGE_KIND_COUNT = 8


def run_evaluation() -> dict[str, Any]:
    engine = M2506RobustnessEngine()
    supported = engine.challenge(build_request())
    abstained = engine.challenge(
        build_request(disposition=ChallengeDisposition.ABSTAIN_UNSUPPORTED)
    )
    reviewed = engine.challenge(build_request(disposition=ChallengeDisposition.REVIEW_REQUIRED))
    replayed = engine.replay(supported)
    deterministic = engine.challenge(build_request()).result_digest == supported.result_digest
    checks = {
        "supported_evaluated": supported.status is RobustnessStatus.EVALUATED,
        "surface_has_eight_kinds": (
            supported.robustness_surface is not None
            and len(supported.robustness_surface.observations) == _CHALLENGE_KIND_COUNT
        ),
        "unsupported_abstained": abstained.status is RobustnessStatus.ABSTAINED,
        "review_abstained": reviewed.status is RobustnessStatus.ABSTAINED,
        "safe_failure_present": abstained.safe_failure_report is not None,
        "replay_verified": replayed.result_digest == supported.result_digest,
        "deterministic": deterministic,
        "no_parent_emission": supported.emits_parent is False,
    }
    return {
        "module": "M25-06",
        "scenario_count": 8,
        "checks": checks,
        "passed": all(checks.values()),
        "fixture": "m25_06_robustness_v1",
        "supported_result_digest": supported.result_digest,
    }


__all__ = ["run_evaluation"]
