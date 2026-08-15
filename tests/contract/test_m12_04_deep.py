"""Contract, runtime, replay, safety, and plugin tests for M12-04."""

# The adversarial matrix intentionally uses broad boundary exceptions and
# literal protocol values to verify fail-closed behavior.
# ruff: noqa: E501, B017, PT011, PT018, TRY003

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m12_04 import (
    M1204_M1201_RESULT_MEDIA_TYPE,
    M1204_MODULE_ID,
    InferBiomarkerPanelMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismFindingCode,
    MechanismInferenceConfiguration,
    MechanismInferenceStatus,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
    assert engine.verify(result, replay=False) == result


def test_plugin_requires_issued_parse_once_token() -> None:
    plugin = M1204Plugin(M1204Service())
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
