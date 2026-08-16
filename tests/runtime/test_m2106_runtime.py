"""Runtime, replay, and fail-closed preflight tests for provisional M21-06."""

from __future__ import annotations

import json

import pytest

from glio_proteogen.contracts.m21_06 import (
    ChallengeComplexActivityRobustnessRequest,
    ChallengeDisposition,
    RobustnessStatus,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c21_reference_material.m21_06_robustness_shift_ood_challenge import (
    M2106AuthorizationError,
    M2106Engine,
    M2106ReplayError,
    M2106Service,
)
from tests.adversarial.test_m2106_adversarial import _request

_SCENARIO_COUNT = 8


def _supported_request() -> ChallengeComplexActivityRobustnessRequest:
    payload = _request().model_dump(mode="python")
    for scenario in payload["scenarios"]:
        scenario["expected_disposition"] = (
            ChallengeDisposition.WITHIN_ENVELOPE
            if scenario["kind"].value == "low_input"
            else ChallengeDisposition.REVIEW_REQUIRED
        )
    return ChallengeComplexActivityRobustnessRequest(**payload)


def test_engine_abstains_for_unsupported_declarations_without_surface() -> None:
    result = M2106Engine().generate(_request())
    assert result.status is RobustnessStatus.ABSTAINED
    assert result.robustness_surface is None
    assert result.safe_failure_report is not None
    assert result.support_decision.status.value == "unsupported"


def test_engine_evaluates_supported_surface_and_replays() -> None:
    engine = M2106Engine()
    result = engine.generate(_supported_request())
    assert result.status is RobustnessStatus.EVALUATED
    assert result.robustness_surface is not None
    assert len(result.robustness_surface.observations) == _SCENARIO_COUNT
    replay = engine.replay(result)
    assert replay.result_digest == result.result_digest


def test_replay_rejects_tampered_result_digest() -> None:
    result = M2106Engine().generate(_supported_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(M2106ReplayError, match="payload digest"):
        M2106Engine().replay(tampered)


def test_authorization_fails_before_mapping_execution() -> None:
    payload = _supported_request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD
    denied = ChallengeComplexActivityRobustnessRequest(**payload)
    with pytest.raises(M2106AuthorizationError):
        M2106Engine().generate(denied)


def test_service_and_json_input_share_the_canonical_path() -> None:
    service = M2106Service()
    request = _supported_request()
    encoded = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    typed = service.validate_request(request)
    from_json = service.validate_request(encoded)
    assert typed == from_json
    assert service.generate(typed).result_digest == service.generate(from_json).result_digest
