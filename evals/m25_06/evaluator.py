"""Executable M25-06 evaluator matrix with deterministic assertions."""

from __future__ import annotations

from typing import Any

from glio_proteogen.contracts.m25_06 import ChallengeDisposition, RobustnessStatus
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m25_06_robustness_shift_ood_challenge import (
    M2506RobustnessEngine,
)

from .fixture import build_request

_CHALLENGE_KIND_COUNT = 8
_AUTHORITY = "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
_SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:8833-8875"


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
        "module_id": "GLIO-PROTEOGEN-M25-06",
        "dossier_sha256": _AUTHORITY,
        "dossier_slice": _SLICE,
        "parent_target": "proteotype",
        "upstream_dependency": "M25-04 caller-declared media only",
        "scenario_count": _CHALLENGE_KIND_COUNT,
        "adversarial_case_count": len(checks),
        "adversarial_passed_count": sum(checks.values()),
        "checks": checks,
        "passed": all(checks.values()),
        "fixture": "m25_06_robustness_v1",
        "fixture_digest": sha256_digest(build_request()),
        "supported_result_digest": supported.result_digest,
    }


__all__ = ["run_evaluation"]
