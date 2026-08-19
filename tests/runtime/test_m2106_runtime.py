"""Runtime, replay, and fail-closed preflight tests for provisional M21-06."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import pytest

from glio_proteogen.contracts.m21_06 import (
    ChallengeComplexActivityRobustnessRequest,
    ChallengeDisposition,
    ChallengeFindingCode,
    OODBand,
    RobustnessStatus,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c21_reference_material.m21_06_robustness_shift_ood_challenge import (
    M2106AuthorizationError,
    M2106Engine,
    M2106ReplayError,
    M2106Service,
    preflight_m2106_authorization,
    run_complex_activity_robustness_challenge,
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


def test_ood_threshold_controls_bands_and_safe_abstention() -> None:
    engine = M2106Engine()
    base = _supported_request()
    lowered = base.model_copy(
        update={
            "configuration": base.configuration.model_copy(update={"ood_threshold": 0.7})
        }
    )
    evaluated = engine.generate(lowered)
    assert evaluated.status is RobustnessStatus.EVALUATED
    assert evaluated.robustness_surface is not None
    assert any(
        observation.ood_band is OODBand.OUT_OF_DOMAIN
        for observation in evaluated.robustness_surface.observations
        if observation.disposition is ChallengeDisposition.REVIEW_REQUIRED
    )

    strict = lowered.model_copy(
        update={
            "configuration": lowered.configuration.model_copy(update={"ood_threshold": 0.05})
        }
    )
    abstained = engine.generate(strict)
    assert abstained.status is RobustnessStatus.ABSTAINED
    assert abstained.robustness_surface is None
    assert any(item.code is ChallengeFindingCode.OOD_STATE for item in abstained.findings)
    assert engine.replay(abstained).result_digest == abstained.result_digest


def test_replay_rejects_tampered_result_digest() -> None:
    result = M2106Engine().generate(_supported_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(M2106ReplayError, match="payload digest"):
        M2106Engine().replay(tampered)


def test_replay_closes_request_and_result_identity_and_public_entrypoint() -> None:
    request = _supported_request()
    result = M2106Engine().generate(request)
    with pytest.raises(M2106ReplayError, match="request digest"):
        M2106Engine().replay(result.model_copy(update={"request_digest": "sha256:" + "a" * 64}))
    with pytest.raises(M2106ReplayError, match="identifier"):
        M2106Engine().replay(result.model_copy(update={"result_id": "m2106.result.tampered"}))
    assert run_complex_activity_robustness_challenge(request).result_digest == result.result_digest


def test_preflight_fails_closed_for_hostile_mappings() -> None:
    class HostileMapping(Mapping[str, object]):
        def get(self, _field: str, _default: object = None) -> object:
            raise RuntimeError("hostile mapping")  # noqa: TRY003

        def __getitem__(self, _key: str) -> object:
            raise RuntimeError("hostile mapping")  # noqa: TRY003

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

    with pytest.raises(M2106AuthorizationError):
        preflight_m2106_authorization(HostileMapping())


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
