"""Runtime, replay and safe-boundary tests for M20-04."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m20_04 import (
    M2004_M2003_INPUT_MEDIA_TYPE,
    AdapterFindingCode,
    AdapterStatus,
    IntendedUseKind,
    PolicyDecisionStatus,
)
from glio_proteogen.contracts.m20_04.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m20_04_intended_use_adapter as m2004,
)
from tests.contract.test_m20_04_hardening import _request


def test_supported_registration_adapts_and_replays_deterministically() -> None:
    request = _request()
    engine = m2004.M2004Engine()
    first = engine.adapt(request)
    second = engine.adapt(request.model_dump(mode="python"))

    assert first.status is AdapterStatus.ADAPTED
    assert first.adapted_object is not None
    assert first.policy_decision.status is PolicyDecisionStatus.ALLOWED
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert first.result_digest == second.result_digest
    assert engine.replay(first) == first


def test_treatment_claim_abstains_without_adapted_object() -> None:
    request = _request()
    registration = request.registration.model_copy(
        update={
            "claim_ceiling": request.registration.claim_ceiling.model_copy(
                update={"maximum_claim": "Treatment recommendation for subtype selection."}
            )
        }
    )
    result = m2004.M2004Engine().adapt(request.model_copy(update={"registration": registration}))

    assert result.status is AdapterStatus.ABSTAINED
    assert result.adapted_object is None
    assert result.human_review_required is True
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert any(
        finding.code is AdapterFindingCode.TREATMENT_RECOMMENDATION_BLOCKED
        for finding in result.findings
    )


def test_clinical_review_with_low_tier_abstains_and_preserves_finding() -> None:
    request = _request()
    registration = request.registration.model_copy(
        update={"intended_use": IntendedUseKind.CLINICAL_REVIEW, "evidence_tier": 2}
    )
    result = m2004.M2004Engine().adapt(request.model_copy(update={"registration": registration}))

    assert result.status is AdapterStatus.ABSTAINED
    assert any(
        finding.code is AdapterFindingCode.EVIDENCE_TIER_MISSING for finding in result.findings
    )
    assert result.policy_decision.status is PolicyDecisionStatus.REVIEW_REQUIRED


def test_preflight_rejects_control_denial_before_adaptation() -> None:
    request = _request()
    denied = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": denied})}
    )
    with pytest.raises(m2004.M2004AuthorizationError, match="control support"):
        m2004.preflight_m2004_authorization(request.model_copy(update={"context": context}))


def test_upstream_media_and_tamper_replay_are_closed() -> None:
    request = _request()
    assert request.upstream_result.media_type == M2004_M2003_INPUT_MEDIA_TYPE
    engine = m2004.M2004Engine()
    result = engine.adapt(request)
    with pytest.raises(m2004.M2004ReplayError, match="payload digest"):
        engine.replay(result.model_copy(update={"human_review_required": True}))


def test_replay_rejects_self_rehashed_semantic_mutation() -> None:
    engine = m2004.M2004Engine()
    result = engine.adapt(_request())
    mutated = result.model_copy(
        update={
            "limitations": (
                *result.limitations,
                Limitation(code="forged", statement="forged semantic state"),
            )
        }
    )
    mutated = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
    with pytest.raises(m2004.M2004ReplayError, match="semantic replay"):
        engine.replay(mutated)


def test_provenance_binds_nested_registration_evidence_artifact_identity() -> None:
    request = _request()
    base_evidence = request.registration.evidence[0]

    def with_digest(label: str) -> EvidenceReference:
        reference = base_evidence.reference.model_copy(
            update={"artifact_id": f"artifact.m2004.{label}", "digest": sha256_digest(label)}
        )
        return base_evidence.model_copy(update={"reference": reference})

    registration = request.registration.model_copy(
        update={
            "evidence": (with_digest("registration"),),
            "claim_ceiling": request.registration.claim_ceiling.model_copy(
                update={"evidence": (with_digest("claim-ceiling"),)}
            ),
            "display_semantics": request.registration.display_semantics.model_copy(
                update={"evidence": (with_digest("display-semantics"),)}
            ),
        }
    )
    result = m2004.M2004Engine().adapt(request.model_copy(update={"registration": registration}))
    input_digests = set(result.provenance.input_digests)

    assert all(
        evidence.reference.digest in input_digests
        for evidence in (
            registration.evidence[0],
            registration.claim_ceiling.evidence[0],
            registration.display_semantics.evidence[0],
        )
    )


def test_service_and_plugin_keep_same_typed_boundary() -> None:
    request = _request()
    service = m2004.M2004Service()
    plugin = m2004.M2004Plugin()
    assert service.validate_request(request) == request
    assert plugin.validate_request(request) == request
    result = plugin.run(request)
    assert plugin.replay(result) == result
    assert plugin.descriptor.external_content_traversal is False
    assert plugin.descriptor.treatment_recommendation is False
    assert plugin.descriptor.claim_ceiling_required is True
