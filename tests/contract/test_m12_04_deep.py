"""Contract, runtime, replay, safety, and plugin tests for M12-04."""

# The adversarial matrix intentionally uses broad boundary exceptions and
# literal protocol values to verify fail-closed behavior.
# ruff: noqa: E501, ARG005, B017, PLR2004, PT011, PT018, PT006, PT007, TRY003

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import glio_proteogen.modules.c12_driver_to_protein_consequence.m12_04_network_state_mechanism_inference.engine as engine_module
from glio_proteogen.contracts.m12_04 import (
    M1204_M1201_RESULT_MEDIA_TYPE,
    M1204_MODULE_ID,
    BiomarkerPanelMechanismInferenceResult,
    InferBiomarkerPanelMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismFindingCode,
    MechanismInferenceConfiguration,
    MechanismInferenceStatus,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.contracts.m12_04.canonical import normalized_request
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c12_driver_to_protein_consequence.m12_04_network_state_mechanism_inference import (
    M1204MechanismAuthorizationError,
    M1204MechanismEngine,
    M1204Plugin,
    M1204ReplayVerificationError,
    M1204Service,
    ValidatedM1204Request,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1204": label}),
        media_type=media_type,
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.configuration",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.configuration"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=sha256_digest("identity"),
            evidence=_artifact("control.identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended"),
        ),
    )


def _request(
    method: str = "posterior:mechanism-a:Candidate mechanism:0.80:0.70:0.90",
    *,
    accepted: bool = True,
) -> InferBiomarkerPanelMechanismRequest:
    configuration = MechanismInferenceConfiguration(
        configuration_id="configuration.m1204",
        version="1.0.0",
        method=method,
        model_reference=_artifact("model", "application/vnd.glio-proteogen.model+json"),
        calibration_reference=_artifact(
            "calibration", "application/vnd.glio-proteogen.calibration+json"
        ),
        evidence=(
            EvidenceReference(
                reference=_artifact("configuration.evidence"),
                role="evidence",
                claim="Locked method and calibration manifest.",
            ),
        ),
    )
    return InferBiomarkerPanelMechanismRequest(
        request_id="request.m1204",
        context=ExecutionContext(
            request_id="request.m1204",
            actor_id="actor.test",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        hypothesis_registry_result=_artifact("m1201-result", M1204_M1201_RESULT_MEDIA_TYPE),
        configuration=configuration,
        source_artifacts=(_artifact("counter-evidence"),),
    )


def test_supported_posterior_is_typed_and_replayable() -> None:
    engine = M1204MechanismEngine()
    result = engine.infer(_request())
    assert result.status is MechanismInferenceStatus.INFERRED
    assert result.estimates[0].kind is MechanismEstimateKind.POSTERIOR
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.provenance.module_id == M1204_MODULE_ID
    assert result.parent_target == "biomarker_panel"
    assert engine.verify(result).model_dump(mode="json") == result.model_dump(mode="json")


def test_state_method_preserves_alternatives_and_counter_evidence() -> None:
    result = M1204MechanismEngine().infer(_request("state:mechanism-b:State mechanism:active"))
    assert result.status is MechanismInferenceStatus.INFERRED
    estimate = result.estimates[0]
    assert estimate.state_value == "active"
    assert estimate.alternatives and estimate.counter_evidence


@pytest.mark.parametrize(
    "method",
    ["abstain:review", "bayesian_graph:mechanism:label", "posterior:m:x:0.95:0.10:0.20"],
)
def test_unknown_or_invalid_method_abstains_without_negative_finding(method: str) -> None:
    result = M1204MechanismEngine().infer(_request(method))
    assert result.status is MechanismInferenceStatus.ABSTAINED
    assert result.estimates == ()
    assert result.human_review_required is True
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert all(
        item.code is not MechanismFindingCode.UPSTREAM_UNSUPPORTED for item in result.findings
    )


def test_control_denial_fails_before_typed_materialization() -> None:
    with pytest.raises(M1204MechanismAuthorizationError):
        M1204MechanismEngine().infer(_request(accepted=False))


def test_hostile_candidate_fails_closed() -> None:
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("must not traverse hostile payload")

    with pytest.raises(M1204MechanismAuthorizationError):
        M1204MechanismEngine().infer(Hostile())


def test_tampered_digest_is_rejected_and_replay_can_be_disabled() -> None:
    engine = M1204MechanismEngine()
    result = engine.infer(_request())
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    with pytest.raises(M1204ReplayVerificationError):
        engine.verify(tampered)
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            engine_module,
            "result_payload_digest",
            lambda value: "sha256:" + "e" * 64,
        )
        with pytest.raises(M1204ReplayVerificationError):
            engine.verify(result)
    finally:
        monkeypatch.undo()
    monkeypatch = pytest.MonkeyPatch()
    original_infer = engine_module.M1204MechanismEngine.infer
    try:
        monkeypatch.setattr(
            engine_module.M1204MechanismEngine,
            "infer",
            lambda self, request: original_infer(self, _request("state:other:Other:active")),
        )
        with pytest.raises(M1204ReplayVerificationError):
            engine.verify(result)
    finally:
        monkeypatch.undo()
    assert engine.verify(result, replay=False) == result


def test_plugin_requires_issued_parse_once_token() -> None:
    plugin = M1204Plugin(M1204Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M12-04"
    token = plugin.validate(_request())
    result = plugin.run(token)
    assert result.status is MechanismInferenceStatus.INFERRED
    assert isinstance(token, ValidatedM1204Request)
    forged = ValidatedM1204Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)


def test_plugin_strict_json_rejects_duplicate_keys() -> None:
    plugin = M1204Plugin(M1204Service())
    payload = _request().model_dump_json()
    duplicate = payload[:-1] + ',"request_id":"request.other"}'
    with pytest.raises(Exception):  # strict scanner type is intentionally opaque at this boundary
        plugin.validate(duplicate)


def test_estimate_contract_rejects_missing_counter_evidence() -> None:
    with pytest.raises(ValueError, match="at least 1 item"):
        MechanismEstimate(
            estimate_id="estimate.one",
            mechanism_id="mechanism.one",
            label="Mechanism",
            kind=MechanismEstimateKind.POSTERIOR,
            posterior_probability=0.8,
            lower_bound=0.7,
            upper_bound=0.9,
            assumptions=("An explicit assumption.",),
            alternatives=("An explicit alternative.",),
            counter_evidence=(),
        )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"kind": MechanismEstimateKind.POSTERIOR}, "posterior estimate"),
        (
            {
                "kind": MechanismEstimateKind.STATE,
                "state_value": "active",
                "posterior_probability": 0.2,
            },
            "state estimate",
        ),
        (
            {"kind": MechanismEstimateKind.STATE, "state_value": "active", "lower_bound": 0.1},
            "state estimate",
        ),
    ],
)
def test_estimate_shape_invariants_are_closed(kwargs: dict[str, object], message: str) -> None:
    base: dict[str, object] = {
        "estimate_id": "estimate.invalid",
        "mechanism_id": "mechanism.invalid",
        "label": "Invalid",
        "assumptions": ("assumption",),
        "alternatives": ("alternative",),
        "counter_evidence": (
            {"reference": _artifact("counter"), "role": "evidence", "claim": "counter"},
        ),
    }
    with pytest.raises(ValueError, match=message):
        MechanismEstimate(**(base | kwargs))


def test_request_media_and_result_closure_reject_forgery() -> None:
    request = _request()
    forged_request = request.model_dump(mode="python")
    forged_request["hypothesis_registry_result"]["media_type"] = "application/octet-stream"  # type: ignore[index]
    with pytest.raises(ValueError, match="provisional M12-01"):
        InferBiomarkerPanelMechanismRequest.model_validate(forged_request, strict=True)
    result = M1204MechanismEngine().infer(request)

    def resigned(**updates: object) -> dict[str, object]:
        payload = result.model_dump(mode="python")
        payload.update(updates)
        payload["result_digest"] = result_payload_digest(payload)
        return payload

    with pytest.raises(ValueError, match="result identifier"):
        BiomarkerPanelMechanismInferenceResult.model_validate(
            resigned(result_id="result.bad"), strict=True
        )
    with pytest.raises(ValueError, match="request digest"):
        BiomarkerPanelMechanismInferenceResult.model_validate(
            resigned(request_digest="sha256:" + "0" * 64), strict=True
        )
    with pytest.raises(ValueError, match="estimate ids"):
        BiomarkerPanelMechanismInferenceResult.model_validate(
            resigned(estimates=result.estimates + result.estimates), strict=True
        )
    abstained = M1204MechanismEngine().infer(_request("abstain:review"))
    bad_review = {**abstained.model_dump(mode="python"), "human_review_required": False}
    bad_review["result_digest"] = result_payload_digest(bad_review)
    with pytest.raises(ValueError, match="abstained result"):
        BiomarkerPanelMechanismInferenceResult.model_validate(bad_review, strict=True)
    no_evidence = {**result.model_dump(mode="python"), "evidence": ()}
    no_evidence["result_digest"] = result_payload_digest(no_evidence)
    with pytest.raises(ValueError, match="every result"):
        BiomarkerPanelMechanismInferenceResult.model_validate(no_evidence, strict=True)
    duplicated_findings = {
        **abstained.model_dump(mode="python"),
        "findings": abstained.findings + abstained.findings,
    }
    duplicated_findings["result_digest"] = result_payload_digest(duplicated_findings)
    with pytest.raises(ValueError, match="finding ids"):
        BiomarkerPanelMechanismInferenceResult.model_validate(duplicated_findings, strict=True)
    human_review = {**result.model_dump(mode="python"), "human_review_required": True}
    human_review["result_digest"] = result_payload_digest(human_review)
    with pytest.raises(ValueError, match="inferred result"):
        BiomarkerPanelMechanismInferenceResult.model_validate(human_review, strict=True)


def test_uncertainty_and_canonical_dict_projections_are_explicit() -> None:
    supported = expected_uncertainty(supported=True)
    abstained = expected_uncertainty(supported=False)
    assert supported.measurement.probability == 0.9
    assert abstained.measurement.probability is None
    assert len(supported.sensitivity_notes) == 2
    assert normalized_request({"request_id": "dict"}) == {"request_id": "dict"}


@pytest.mark.parametrize(
    "method",
    (
        "posterior:mechanism-a:Candidate:bad:0.1:0.2",
        "posterior:mechanism-a",
        "state:mechanism-a",
        "state:mechanism-a:Label:unknown",
        "posterior:mechanism-a:Candidate:2:0:1",
    ),
)
def test_method_and_numeric_error_matrix_abstains(method: str) -> None:
    result = M1204MechanismEngine().infer(_request(method))
    assert result.status is MechanismInferenceStatus.ABSTAINED
    assert not result.estimates


def test_engine_private_error_and_counter_evidence_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        engine_module._decimal("not-a-number")
    with pytest.raises(ValueError):
        engine_module._decimal("2")
    normal = M1204MechanismEngine().infer(_request())
    request = _request().model_copy(update={"source_artifacts": ()})
    monkeypatch.setattr(
        engine_module,
        "_parse_method",
        lambda method, *, counter_evidence, evidence: (normal.estimates[0], None, None),
    )
    with pytest.raises(ValueError):
        M1204MechanismEngine()._result(request)
    assert (
        engine_module.infer_biomarker_panel_mechanism(_request()).status
        is MechanismInferenceStatus.INFERRED
    )


def test_plugin_bytes_and_service_validation_paths() -> None:
    service = M1204Service()
    plugin = M1204Plugin(service)
    request = _request()
    token = plugin.validate(canonical_json_bytes(request))
    assert plugin.run(token).status is MechanismInferenceStatus.INFERRED
    assert plugin.verify(plugin.run(token)).status is MechanismInferenceStatus.INFERRED
    with pytest.raises(TypeError):
        plugin.run({})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        plugin.validate("{")
    assert service.validate_request(request) == request
    assert service.execute(request).status is MechanismInferenceStatus.INFERRED
