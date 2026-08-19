"""Adversarial and replay coverage for M15-02."""

from __future__ import annotations

from datetime import UTC, datetime
from json import dumps

import pytest

from glio_proteogen.contracts.m15_02 import (
    M1502_M1501_INPUT_MEDIA_TYPE,
    ApplicableMechanism,
    ContextAttribute,
    ContextDimension,
    ContextEvaluationStatus,
    ContextStratificationStatus,
    ContextValueStatus,
    StratifyContextAndSubtypeRequest,
    result_payload_digest,
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
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_02_context_subtype_stratifier as m1502,
)


def _digest(label: str) -> str:
    return sha256_digest({"m1502-test": label})


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1502.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="caller-declared M15-02 test evidence",
    )


def _context() -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role),
        )

    return ExecutionContext(
        request_id="request.m1502",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity-binding"),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _request(
    *,
    status: ContextValueStatus = ContextValueStatus.OBSERVED,
    mechanism_class: str = "contextual_mechanism",
) -> StratifyContextAndSubtypeRequest:
    attribute = ContextAttribute(
        attribute_id="attribute.subtype",
        dimension=ContextDimension.SUBTYPE,
        value="caller_declared_subtype",
        status=status,
        support_basis="reviewed caller declaration",
        evidence=(_evidence("subtype"),),
    )
    mechanism = ApplicableMechanism(
        mechanism_id="mechanism.context",
        mechanism_class=mechanism_class,
        context_attribute_ids=(attribute.attribute_id,),
        rationale="caller-declared applicable mechanism",
        evidence=(_evidence("mechanism"),),
    )
    return StratifyContextAndSubtypeRequest(
        request_id="request.m1502",
        context=_context(),
        upstream_result=ArtifactReference(
            artifact_id="upstream.m1501",
            version="0.1.0-provisional",
            digest=_digest("upstream"),
            media_type=M1502_M1501_INPUT_MEDIA_TYPE,
        ),
        attributes=(attribute,),
        mechanisms=(mechanism,),
        reviewer_id="reviewer.platform",
        source_artifacts=(_artifact("proteome"), _artifact("genome")),
    )


def test_supported_declaration_is_replay_stable_and_non_parent_emitting() -> None:
    service = m1502.M1502Service()
    result = service.execute(_request())
    assert result.status is ContextStratificationStatus.STRATIFIED
    assert result.profile is not None
    assert result.emits_parent is False
    assert result.parent_target == "complex_activity"
    assert all(item.status is ContextEvaluationStatus.SUPPORTED for item in result.evaluations)
    assert service.verify(result).result_digest == result.result_digest


def test_inferred_context_abstains_without_promoting_a_profile() -> None:
    result = m1502.M1502Service().execute(_request(status=ContextValueStatus.INFERRED))
    assert result.status is ContextStratificationStatus.ABSTAINED
    assert result.profile is None
    assert result.support_decision.status.value == "review_required"
    assert result.evaluations[0].status is ContextEvaluationStatus.NOT_EVALUABLE


def test_prohibited_proxy_abstains_and_is_auditable() -> None:
    result = m1502.M1502Service().execute(_request(mechanism_class="kinase activity"))
    assert result.status is ContextStratificationStatus.ABSTAINED
    assert result.findings[0].code.value == "prohibited_proxy"
    assert result.support_decision.status.value == "unsupported"


def test_denied_control_fails_before_request_traversal() -> None:
    request = _request()
    denied = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": ConsentState.WITHHELD}
                    )
                }
            )
        }
    )
    with pytest.raises(m1502.M1502AuthorizationError):
        m1502.M1502Service().execute(request.model_copy(update={"context": denied}))


def test_wrong_upstream_media_type_is_rejected() -> None:
    request = _request().model_dump(mode="python")
    request["upstream_result"]["media_type"] = "application/json"
    with pytest.raises(ValueError, match="M15-01"):
        m1502.M1502Service().construct(request)


def test_tampered_result_fails_replay_verification() -> None:
    result = m1502.M1502Service().execute(_request())
    tampered = result.model_copy(update={"result_id": "result.m1502.tampered"})
    with pytest.raises(m1502.M1502ReplayVerificationError):
        m1502.M1502Service().verify(tampered)


def test_plugin_requires_sealed_validation_token() -> None:
    plugin = m1502.M1502Plugin(m1502.M1502Service())
    validated = plugin.validate(_request())
    assert plugin.run(validated).result_id.startswith("result.m1502.")
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_service_validation_and_preflight_reject_malformed_candidates() -> None:
    service = m1502.M1502Service()
    request = _request()
    assert service.validate_request(request) == request
    assert service.validate_request(request.model_dump(mode="python")) == request
    with pytest.raises(TypeError, match="strict request model"):
        service.validate_request(object())
    with pytest.raises(m1502.M1502AuthorizationError):
        m1502.preflight_m1502_authorization(object())


def test_engine_rejects_non_mapping_candidate_and_deduplicates_evidence() -> None:
    request = _request().model_copy(
        update={"source_artifacts": (_request().upstream_result, *_request().source_artifacts)}
    )
    result = m1502.M1502Service().execute(request)
    assert len(result.evidence) < len(request.source_artifacts) + 20

    class _Candidate:
        context = request.context

    with pytest.raises(TypeError, match="strict request model"):
        m1502.M1502ContextStratifierEngine().construct(_Candidate())


def test_plugin_json_and_verify_paths_are_strict() -> None:
    plugin = m1502.M1502Plugin(m1502.M1502Service())
    validated = plugin.validate(_request().model_dump_json())
    result = plugin.run(validated)
    assert plugin.verify(result).result_id == result.result_id


def test_plugin_json_preflights_authorization_before_nested_contract_validation() -> None:
    plugin = m1502.M1502Plugin(m1502.M1502Service())
    payload = _request().model_dump(mode="json")
    references = payload["context"]["references"]
    assert isinstance(references, dict)
    consent = references["consent"]
    assert isinstance(consent, dict)
    consent["state"] = "withheld"
    attributes = payload["attributes"]
    assert isinstance(attributes, list)
    attributes[0]["unexpected"] = "mask-authorization"

    with pytest.raises(m1502.M1502AuthorizationError):
        plugin.validate(dumps(payload))


def test_replay_detects_digest_valid_but_semantically_tampered_result() -> None:
    service = m1502.M1502Service()
    result = service.execute(_request())
    tampered = result.model_copy(update={"human_review_required": False})
    tampered = tampered.model_copy(
        update={"result_digest": result_payload_digest(tampered)}
    )
    with pytest.raises(m1502.M1502ReplayVerificationError):
        service.verify(tampered)
