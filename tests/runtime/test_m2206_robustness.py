"""Runtime, service and strict-plugin tests for M22-06."""

# ruff: noqa: PLR2004

from __future__ import annotations

from typing import Any, cast

import pytest

from glio_proteogen.contracts.m22_06 import (
    ChallengeDisposition,
    RobustnessStatus,
)
from glio_proteogen.contracts.m22_06.canonical import result_payload_digest
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m22_06_robustness_shift_ood_challenge import (
    M2206AuthorizationError,
    M2206Engine,
    M2206Plugin,
    M2206ReplayError,
    M2206Service,
    challenge_protein_rna_discordance_robustness,
)
from tests.adversarial.test_m2206_contract_adversarial import _request


def test_supported_surface_is_evaluated_and_replayable() -> None:
    engine = M2206Engine()
    result = engine.evaluate(_request())
    assert result.status is RobustnessStatus.EVALUATED
    assert result.robustness_surface is not None
    assert result.safe_failure_report is None
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert len(result.robustness_surface.observations) == 8
    assert engine.verify(result).result_digest == result.result_digest


@pytest.mark.parametrize(
    "disposition",
    [ChallengeDisposition.REVIEW_REQUIRED, ChallengeDisposition.ABSTAIN_UNSUPPORTED],
)
def test_review_and_unsupported_challenges_abstain_safely(
    disposition: ChallengeDisposition,
) -> None:
    request = _request()
    scenario = request.scenarios[0].model_copy(update={"expected_disposition": disposition})
    candidate = request.model_copy(update={"scenarios": (scenario, *request.scenarios[1:])})
    result = M2206Engine().evaluate(candidate)
    assert result.status is RobustnessStatus.ABSTAINED
    assert result.robustness_surface is None
    assert result.safe_failure_report is not None
    assert result.abstention_reason is not None
    assert result.support_decision.status in {
        SupportStatus.UNSUPPORTED,
        SupportStatus.REVIEW_REQUIRED,
    }
    assert result.findings


def test_denied_controls_and_malformed_input_fail_closed() -> None:
    request = _request()
    denied = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    refs = request.context.references.model_copy(update={"support": denied})
    candidate = request.model_copy(
        update={"context": request.context.model_copy(update={"references": refs})}
    )
    with pytest.raises(M2206AuthorizationError):
        M2206Engine().evaluate(candidate)
    with pytest.raises(M2206AuthorizationError):
        M2206Engine().evaluate({"request_id": "invalid"})


def test_service_plugin_replay_and_public_entrypoint_parity() -> None:
    request = _request()
    service = M2206Service()
    typed = service.validate_request(request)
    result = service.execute(typed)
    assert service.verify(result).result_id == result.result_id
    plugin = M2206Plugin(service)
    token = plugin.validate(request.model_dump_json())
    assert plugin.run(token).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M22-06"
    with pytest.raises(TypeError):
        plugin.run(cast("Any", request))
    public = challenge_protein_rna_discordance_robustness(request)
    assert public == result


def test_plugin_rejects_nested_request_mutation() -> None:
    request = _request()
    plugin = M2206Plugin()
    token = plugin.validate(request)
    object.__setattr__(token.request, "request_id", "m2206.tampered")
    with pytest.raises(TypeError):
        plugin.run(token)


def test_replay_rejects_tampered_payload() -> None:
    engine = M2206Engine()
    result = engine.evaluate(_request())
    with pytest.raises(M2206ReplayError):
        engine.verify(result.model_copy(update={"abstention_reason": "tampered"}), replay=False)
    with pytest.raises((TypeError, ValueError)):
        M2206Plugin().validate("{")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("module_id", "GLIO-PROTEOGEN-M22-05"),
        ("module_version", "9.9.9"),
        ("configuration_digest", "sha256:" + "f" * 64),
        ("input_digests", ("sha256:" + "f" * 64,)),
    ],
)
def test_replay_rejects_self_rehashed_provenance_binding_mutations(
    field: str,
    value: object,
) -> None:
    engine = M2206Engine()
    result = engine.evaluate(_request())
    forged = result.model_copy(
        update={"provenance": result.provenance.model_copy(update={field: value})}
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    with pytest.raises(M2206ReplayError):
        engine.verify(forged)
