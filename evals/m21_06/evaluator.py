"""Executable M21-06 robustness and shift evaluator matrix."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from glio_proteogen.contracts.m21_06 import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m21_06_robustness_shift_ood_challenge import (
    M2106AuthorizationError,
    M2106ReplayError,
    M2106Service,
)

from .fixture import build_request, supported_request

if TYPE_CHECKING:
    from glio_proteogen.contracts.m21_06 import ChallengeComplexActivityRobustnessRequest

_SCENARIO_COUNT = 8


def _denied_request() -> ChallengeComplexActivityRobustnessRequest:
    request = supported_request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": rejected})}
    )
    return request.model_copy(update={"context": context})


def run_evaluator() -> dict[str, Any]:
    """Run deterministic supported, mixed, replay, and fail-closed scenarios."""

    service = M2106Service()
    request = supported_request()
    result = service.generate(request)
    repeated = service.generate(request)
    mixed = service.generate(build_request())
    observations = result.robustness_surface.observations if result.robustness_surface else ()
    expected_input_digests = (
        {artifact.digest for artifact in request.source_artifacts}
        | {item.reference.digest for item in request.configuration.evidence}
        | {
            artifact.digest
            for scenario in request.scenarios
            for artifact in scenario.source_artifacts
        }
        | {item.reference.digest for scenario in request.scenarios for item in scenario.evidence}
    )
    checks: dict[str, bool] = {
        "supported_evaluated": result.status.value == "evaluated",
        "all_locked_scenarios_observed": len(observations) == _SCENARIO_COUNT,
        "within_and_review_dispositions": {item.disposition.value for item in observations}
        == {"within_envelope", "review_required"},
        "ood_bands_are_bounded": all(0.0 <= item.ood_score <= 1.0 for item in observations),
        "seven_axis_uncertainty_present": result.uncertainty is not None,
        "provenance_covers_bound_material": expected_input_digests
        <= set(result.provenance.input_digests),
        "deterministic_result": result.result_digest == repeated.result_digest,
        "replay_verified": service.replay(result).result_digest == result.result_digest,
        "mixed_support_abstains_safely": (
            mixed.status.value == "abstained"
            and mixed.robustness_surface is None
            and mixed.safe_failure_report is not None
        ),
        "parent_boundary_closed": (
            result.emits_parent is False and result.parent_target == "complex activity"
        ),
    }
    try:
        service.generate(_denied_request())
    except M2106AuthorizationError:
        checks["support_control_fail_closed"] = True
    else:
        checks["support_control_fail_closed"] = False
    tampered = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"rationale": "forged support rationale"}
            )
        }
    )
    tampered = type(tampered).model_construct(
        **{**tampered.__dict__, "result_digest": result_payload_digest(tampered)}
    )
    try:
        service.replay(tampered)
    except M2106ReplayError:
        checks["tamper_rejected"] = True
    else:
        checks["tamper_rejected"] = False
    return {
        "module": "M21-06",
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
