"""Runtime, replay, service, and capability tests for M25-08."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m25_08.fixture import build_request, denied_request

from glio_proteogen.contracts.m25_08 import (
    ApprovalDecision,
    GateRunStatus,
    RiskSeverity,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m25_08_evidence_gate_release_adjudicator import (
    M2508AuthorizationError,
    M2508Engine,
    M2508EvaluationError,
    M2508Plugin,
    M2508ReplayError,
    M2508Service,
    ValidatedM2508Request,
    adjudicate_proteotype_evidence_gate,
)


def test_nominal_gate_is_adjudicated_and_replayable() -> None:
    engine = M2508Engine()
    result = engine.evaluate(build_request())
    assert result.status is GateRunStatus.ADJUDICATED
    assert result.release_record is not None
    assert result.release_record.decision.value == "pass"
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False
    assert result.human_review_required is True
    assert engine.verify(result).result_digest == result.result_digest


@pytest.mark.parametrize(
    "update",
    [
        {
            "requirements": (
                build_request().requirements[0].model_copy(update={"satisfied": False}),
            )
        },
        {"benchmarks": (build_request().benchmarks[0].model_copy(update={"passed": False}),)},
        {
            "residual_risks": (
                build_request()
                .residual_risks[0]
                .model_copy(update={"severity": RiskSeverity.CRITICAL, "accepted": False}),
            )
        },
        {
            "approvals": (
                build_request()
                .approvals[0]
                .model_copy(update={"decision": ApprovalDecision.DEFER}),
            )
        },
    ],
)
def test_gate_failures_abstain_without_release_record(update: dict[str, object]) -> None:
    result = M2508Engine().evaluate(build_request().model_copy(update=update))
    assert result.status is GateRunStatus.ABSTAINED
    assert result.release_record is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.abstention_reason is not None
    assert result.findings


@pytest.mark.parametrize(
    "field",
    ["approved_configuration", "provenance", "quality", "support", "intended_use"],
)
def test_denied_control_fails_before_gate_traversal(field: str) -> None:
    request = build_request()
    decision = request.context.references.__getattribute__(field)
    denied = decision.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    references = request.context.references.model_copy(update={field: denied})
    candidate = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    with pytest.raises(M2508AuthorizationError):
        M2508Engine().evaluate(candidate)


def test_consent_and_malformed_request_are_safe_failures() -> None:
    request = build_request()
    consent = request.context.references.consent.model_copy(update={"state": "revoked"})
    refs = request.context.references.model_copy(update={"consent": consent})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": refs})}
    )
    with pytest.raises(M2508AuthorizationError):
        M2508Engine().evaluate(denied)
    with pytest.raises(M2508AuthorizationError):
        M2508Engine().evaluate({"request_id": "invalid"})


def test_service_and_plugin_share_strict_parse_once_boundary() -> None:
    request = build_request()
    service = M2508Service()
    validated = service.validate_request(request)
    result = service.execute(validated)
    assert service.verify(result).result_id == result.result_id
    plugin = M2508Plugin(service)
    token = plugin.validate(request.model_dump_json())
    assert isinstance(token, ValidatedM2508Request)
    assert plugin.run(token).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M25-08"
    assert plugin.descriptor().owner == "Platform engineering"
    with pytest.raises(TypeError):
        plugin.run(cast("Any", request))
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(object())


def test_plugin_tokens_are_instance_bound_and_snapshot_bound() -> None:
    first = M2508Plugin()
    second = M2508Plugin()
    token = first.validate(build_request())

    assert first.run(token).result_digest.startswith("sha256:")
    with pytest.raises(TypeError):
        second.run(token)

    forged = ValidatedM2508Request(request=token.request, _seal=object())
    with pytest.raises(TypeError):
        first.run(forged)

    replaced = first.validate(build_request())
    object.__setattr__(replaced, "request", replaced.request.model_copy())
    with pytest.raises(TypeError):
        first.run(replaced)

    mutated = first.validate(build_request())
    object.__setattr__(mutated.request.requirements[0], "statement", "forged requirement")
    with pytest.raises(TypeError):
        first.run(mutated)


def test_service_accepts_mapping_and_canonical_json() -> None:
    request = build_request()
    service = M2508Service()
    encoded = canonical_json_bytes(request.model_dump(mode="json"))
    from_mapping = service.execute(request.model_dump(mode="json"))
    from_json = service.execute(encoded)
    assert from_mapping == from_json
    assert service.verify(from_json.model_dump(mode="json")) == from_json
    assert service.verify(from_json.model_dump_json()) == from_json


def test_replay_rejects_payload_and_request_tampering() -> None:
    engine = M2508Engine()
    result = engine.evaluate(build_request())
    with pytest.raises(M2508ReplayError):
        engine.verify(result.model_copy(update={"abstention_reason": "tampered"}), replay=False)
    changed = build_request().model_copy(update={"request_id": "request.m2508.changed"})
    with pytest.raises(M2508ReplayError):
        engine.verify(result.model_copy(update={"request": changed}), replay=False)
    with pytest.raises(M2508ReplayError):
        engine.verify(
            result.model_copy(update={"result_digest": sha256_digest("tampered")}), replay=False
        )
    forged = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"rationale": "Forged release approval."}
            )
        }
    )
    forged = type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )
    with pytest.raises(M2508ReplayError, match="replay"):
        engine.verify(forged)
    with pytest.raises(M2508ReplayError, match="cannot be disabled"):
        engine.verify(result, replay=False)


def test_public_function_and_invalid_result_are_closed() -> None:
    result = adjudicate_proteotype_evidence_gate(build_request())
    assert result.status is GateRunStatus.ADJUDICATED
    with pytest.raises(M2508ReplayError):
        M2508Engine().verify({"result_id": "invalid"})
    invalid = build_request().model_dump(mode="python")
    invalid.pop("benchmarks")
    with pytest.raises(M2508EvaluationError):
        M2508Engine().evaluate(invalid)


def test_plugin_validates_typed_request_and_verifies_json_result() -> None:
    request = build_request()
    plugin = M2508Plugin()
    token = plugin.validate(request)
    result = plugin.run(token)
    assert plugin.verify(result.model_dump_json()).result_id == result.result_id


def test_denied_fixture_is_never_converted_to_negative_gate_evidence() -> None:
    with pytest.raises(M2508AuthorizationError):
        M2508Engine().evaluate(denied_request())
