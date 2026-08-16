"""Runtime, replay and plugin gates for the provisional M18-04 adapter."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m18_04 import (
    AdapterStatus,
    IntendedUseKind,
    IntendedUseRegistration,
    PolicyDecisionStatus,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_04_intended_use_adapter as m1804,
)
from tests.contract.test_m18_04_deep import _registration, _request

_CONTROL_COUNT = 7


def test_supported_research_request_emits_bounded_object() -> None:
    result = m1804.M1804Engine().adapt(_request())

    assert result.status is AdapterStatus.ADAPTED
    assert result.adapted_object is not None
    assert result.adapted_object.parent_target == "biomarker panel"
    assert result.adapted_object.registration.registration_id == "registration.m1804"
    assert result.policy_decision.status is PolicyDecisionStatus.ALLOWED
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.emits_parent is False
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.uncertainty.measurement.state.value == "not_estimable"
    assert result.human_review_required is False


def test_clinical_review_is_adapted_but_requires_review() -> None:
    registration = _registration(
        intended_use=IntendedUseKind.CLINICAL_REVIEW,
        evidence_tier=3,
    )
    result = m1804.M1804Engine().adapt(_request(registration))

    assert result.status is AdapterStatus.ADAPTED
    assert result.policy_decision.status is PolicyDecisionStatus.REVIEW_REQUIRED
    assert result.human_review_required is True


@pytest.mark.parametrize(
    "registration",
    [
        _registration(audience="unsupported_audience"),
        _registration(intended_use=IntendedUseKind.CLINICAL_REVIEW, evidence_tier=1),
        _registration(sections=("support", "uncertainty")),
    ],
)
def test_unsafe_policy_inputs_abstain(registration: IntendedUseRegistration) -> None:
    result = m1804.M1804Engine().adapt(_request(registration))

    assert result.status is AdapterStatus.ABSTAINED
    assert result.adapted_object is None
    assert result.policy_decision.status is PolicyDecisionStatus.BLOCKED
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.abstention_reason is not None
    assert result.human_review_required is True
    assert result.findings


def test_treatment_and_forbidden_claims_abstain() -> None:
    request = _request(
        _registration(
            prohibited=("treatment recommendation", "therapy"),
        )
    )
    claim = request.registration.claim_ceiling.model_copy(
        update={"maximum_claim": "Therapeutic treatment recommendation."}
    )
    registration = request.registration.model_copy(update={"claim_ceiling": claim})
    result = m1804.M1804Engine().adapt(_request(registration))

    assert result.status is AdapterStatus.ABSTAINED
    assert {finding.code.value for finding in result.findings} == {
        "treatment_recommendation_blocked",
    }
    assert result.policy_decision.blocked_claims

    forbidden_claim = _registration()
    forbidden_ceiling = forbidden_claim.claim_ceiling.model_copy(
        update={"maximum_claim": "Kinase activity and subtype diagnosis."}
    )
    forbidden = forbidden_claim.model_copy(update={"claim_ceiling": forbidden_ceiling})
    forbidden_result = m1804.M1804Engine().adapt(_request(forbidden))
    assert forbidden_result.status is AdapterStatus.ABSTAINED
    assert any(
        finding.code.value == "claim_exceeds_ceiling" for finding in forbidden_result.findings
    )


def test_preflight_requires_all_controls() -> None:
    with pytest.raises(m1804.M1804AuthorizationError, match="seven upstream controls"):
        m1804.M1804Engine().validate_request({})

    request = _request()
    candidate = request.model_dump(mode="python")
    references = candidate["context"]["references"]
    references["consent"]["state"] = "revoked"
    with pytest.raises(m1804.M1804AuthorizationError, match="consent must be granted"):
        m1804.M1804Engine().validate_request(candidate)


def test_service_replay_rejects_request_and_payload_tamper() -> None:
    service = m1804.M1804Service()
    request = _request()
    assert service.validate_request(request) == request
    result = service.adapt(request)
    assert service.replay(result) == result

    with pytest.raises(m1804.M1804ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "b" * 64}))
    with pytest.raises(m1804.M1804ReplayError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "result.tampered"}))
    with pytest.raises(m1804.M1804ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"human_review_required": True}))


def test_plugin_descriptor_and_strict_validation_parity() -> None:
    plugin = m1804.M1804Plugin()
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M18-04"
    assert plugin.descriptor.provisional_abi is True
    assert plugin.descriptor.intended_use_registration is True
    request = _request()
    assert plugin.validate_request(request) == request
    result = plugin.run(request)
    assert plugin.replay(result) == result
    assert result.status is AdapterStatus.ADAPTED
    with pytest.raises((ValidationError, m1804.M1804AuthorizationError)):
        plugin.validate_request({"request_id": "bad"})
