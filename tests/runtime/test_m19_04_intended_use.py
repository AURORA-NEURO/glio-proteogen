"""Runtime, replay, authorization and plugin gates for M19-04."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_04 import (
    AdapterStatus,
    AdaptProteotypeIntendedUseRequest,
    IntendedUseKind,
    PolicyDecisionStatus,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c19_immunopeptidomic_evidence import (
    m19_04_intended_use_adapter as m1904,
)
from tests.contract.test_m19_04_adversarial import _request as make_request

_CONTROL_COUNT = 7


def _supported_request() -> AdaptProteotypeIntendedUseRequest:
    request = make_request()
    registration = request.registration.model_copy(
        update={
            "audience": "research",
            "intended_use": IntendedUseKind.RESEARCH,
            "evidence_tier": 1,
            "display_semantics": request.registration.display_semantics.model_copy(
                update={
                    "section_order": (
                        "support",
                        "uncertainty",
                        "provenance",
                        "evidence",
                        "limitations",
                    )
                }
            ),
        }
    )
    return request.model_copy(update={"registration": registration})


def test_supported_research_request_emits_bounded_proteotype_object() -> None:
    result = m1904.M1904Engine().adapt(_supported_request())

    assert result.status is AdapterStatus.ADAPTED
    assert result.adapted_object is not None
    assert result.adapted_object.parent_target == "proteotype"
    assert result.adapted_object.registration.intended_use is IntendedUseKind.RESEARCH
    assert result.policy_decision.status is PolicyDecisionStatus.ALLOWED
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.emits_parent is False
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.uncertainty.measurement.state.value == "not_estimable"
    assert result.human_review_required is False


def test_clinical_review_is_adapted_but_requires_review() -> None:
    request = _supported_request()
    registration = request.registration.model_copy(
        update={
            "audience": "clinical_review",
            "intended_use": IntendedUseKind.CLINICAL_REVIEW,
            "evidence_tier": 3,
        }
    )
    result = m1904.M1904Engine().adapt(request.model_copy(update={"registration": registration}))

    assert result.status is AdapterStatus.ADAPTED
    assert result.policy_decision.status is PolicyDecisionStatus.REVIEW_REQUIRED
    assert result.human_review_required is True


@pytest.mark.parametrize(
    "registration_update",
    [
        {"audience": "unsupported_audience"},
        {"intended_use": IntendedUseKind.CLINICAL_REVIEW, "evidence_tier": 1},
        {
            "display_semantics": _supported_request().registration.display_semantics.model_copy(
                update={"section_order": ("support", "uncertainty")}
            )
        },
    ],
)
def test_unsafe_policy_inputs_abstain(registration_update: dict[str, object]) -> None:
    request = _supported_request()
    registration = request.registration.model_copy(update=registration_update)
    result = m1904.M1904Engine().adapt(request.model_copy(update={"registration": registration}))

    assert result.status is AdapterStatus.ABSTAINED
    assert result.adapted_object is None
    assert result.policy_decision.status is PolicyDecisionStatus.BLOCKED
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.abstention_reason is not None
    assert result.human_review_required is True
    assert result.findings


def test_treatment_kinase_and_all_omics_claims_abstain() -> None:
    request = _supported_request()
    ceiling = request.registration.claim_ceiling.model_copy(
        update={
            "maximum_claim": "Kinase activity and direct treatment recommendation.",
            "prohibited_interpretations": ("all-omics fusion",),
        }
    )
    registration = request.registration.model_copy(update={"claim_ceiling": ceiling})
    result = m1904.M1904Engine().adapt(request.model_copy(update={"registration": registration}))

    assert result.status is AdapterStatus.ABSTAINED
    assert result.policy_decision.blocked_claims
    assert {finding.code.value for finding in result.findings} == {
        "treatment_recommendation_blocked",
        "claim_exceeds_ceiling",
    }


def test_preflight_requires_all_controls_and_fail_closed_consent() -> None:
    engine = m1904.M1904Engine()
    with pytest.raises(m1904.M1904AuthorizationError, match="seven upstream controls"):
        engine.validate_request({})

    request = _supported_request()
    candidate = request.model_dump(mode="python")
    references = candidate["context"]["references"]
    references["consent"]["state"] = "revoked"
    with pytest.raises(m1904.M1904AuthorizationError, match="consent must be granted"):
        engine.validate_request(candidate)


def test_service_replay_rejects_request_identifier_and_payload_tamper() -> None:
    service = m1904.M1904Service()
    request = _supported_request()
    assert service.validate_request(request) == request
    result = service.adapt(request)
    assert service.replay(result) == result

    with pytest.raises(m1904.M1904ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "b" * 64}))
    with pytest.raises(m1904.M1904ReplayError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "result.tampered"}))
    with pytest.raises(m1904.M1904ReplayError, match="result digest"):
        service.replay(result.model_copy(update={"human_review_required": True}))


def test_plugin_descriptor_and_strict_validation_parity() -> None:
    plugin = m1904.M1904Plugin()
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M19-04"
    assert plugin.descriptor.parent_target == "proteotype"
    assert plugin.descriptor.owner == "Clinical science"
    assert plugin.descriptor.provisional_abi is True
    assert plugin.descriptor.intended_use_registration is True
    request = _supported_request()
    assert plugin.validate_request(request) == request
    result = plugin.run(request)
    assert plugin.replay(result) == result
    assert result.status is AdapterStatus.ADAPTED
    with pytest.raises((ValidationError, m1904.M1904AuthorizationError)):
        plugin.validate_request({"request_id": "bad"})


def test_plugin_capability_and_direct_run_snapshots_are_instance_bound() -> None:
    request = _supported_request()
    first = m1904.M1904Plugin()
    second = m1904.M1904Plugin()

    token = first.validate(request)
    assert first.run(token).status is AdapterStatus.ADAPTED
    with pytest.raises(TypeError, match="validated request token"):
        second.run(token)

    forged = m1904.ValidatedM1904Request(token.request, object())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(forged)

    replaced = first.validate(request)
    object.__setattr__(replaced, "request", replaced.request.model_copy())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(replaced)

    validated = first.validate_request(_supported_request())
    object.__setattr__(validated.registration, "audience", "forged audience")
    with pytest.raises(TypeError, match="unchanged validated request"):
        first.run(validated)


def test_request_mapping_rejects_coercion_and_wrong_upstream_media_type() -> None:
    request = _supported_request()
    candidate = request.model_dump(mode="python")
    candidate["request_id"] = 17
    with pytest.raises(ValidationError):
        m1904.M1904Engine().validate_request(candidate)

    wrong = request.model_copy(
        update={
            "upstream_result": request.upstream_result.model_copy(
                update={"media_type": "application/json"}
            )
        }
    )
    with pytest.raises(ValidationError, match="M19-03"):
        m1904.M1904Engine().adapt(wrong)
