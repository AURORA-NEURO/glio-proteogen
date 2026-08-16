"""Adversarial contract closure tests for provisional M18-04."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m18_04 import (
    AdaptBiomarkerPanelIntendedUseRequest,
    AdapterFindingCode,
    AdapterStatus,
    BiomarkerPanelIntendedUseAdapterResult,
    ClaimCeiling,
    DisplaySemantics,
    IntendedUseKind,
    IntendedUseRegistration,
    PolicyDecision,
    PolicyDecisionStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m18_04.v1 import M1804_M1803_INPUT_MEDIA_TYPE
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_04_intended_use_adapter as m1804,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)
_EVIDENCE_MEDIA = "application/json"
_SECTIONS = ("support", "uncertainty", "provenance", "evidence", "limitations")


def _artifact(label: str, *, media_type: str = _EVIDENCE_MEDIA) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1804": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="M18-04 intended-use policy evidence",
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Policy adaptation does not estimate biology.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def _context() -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id="request.m1804",
        actor_id="actor.test",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.configuration",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("configuration"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("provenance"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("quality"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("support"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=accepted,
                policy_version="1.0.0",
                evidence=_artifact("intended"),
            ),
        ),
    )


def _registration(
    *,
    intended_use: IntendedUseKind = IntendedUseKind.RESEARCH,
    audience: str = "research",
    evidence_tier: int = 1,
    sections: tuple[str, ...] = _SECTIONS,
    prohibited: tuple[str, ...] = ("treatment recommendation",),
) -> IntendedUseRegistration:
    evidence = (_evidence("registration"),)
    return IntendedUseRegistration(
        registration_id="registration.m1804",
        version="1.0.0",
        intended_use=intended_use,
        audience=audience,
        evidence_tier=evidence_tier,
        claim_ceiling=ClaimCeiling(
            maximum_claim="Descriptive biomarker panel state.",
            prohibited_interpretations=prohibited,
            rationale="Research evidence bounds the claim.",
            evidence=evidence,
        ),
        display_semantics=DisplaySemantics(
            section_order=sections,
            safe_default="Show support, uncertainty, provenance, evidence and limitations.",
            evidence=evidence,
        ),
        evidence=evidence,
    )


def _request(
    registration: IntendedUseRegistration | None = None,
    source_artifacts: tuple[ArtifactReference, ...] | None = None,
) -> AdaptBiomarkerPanelIntendedUseRequest:
    return AdaptBiomarkerPanelIntendedUseRequest(
        request_id="request.m1804",
        context=_context(),
        upstream_result=_artifact("upstream", media_type=M1804_M1803_INPUT_MEDIA_TYPE),
        registration=registration or _registration(),
        source_artifacts=source_artifacts or (_artifact("source"),),
    )


def test_registration_and_display_contracts_are_closed() -> None:
    with pytest.raises(ValidationError, match="section order"):
        _registration(sections=("support", "support"))
    with pytest.raises(ValidationError, match="prohibited interpretations"):
        _registration(prohibited=("treatment", "treatment"))
    with pytest.raises(ValidationError, match="blocked claims"):
        PolicyDecision(
            status=PolicyDecisionStatus.BLOCKED,
            reason_code=AdapterFindingCode.CLAIM_EXCEEDS_CEILING,
            rationale="Blocked.",
            evidence=(_evidence("blocked"),),
        )
    with pytest.raises(ValidationError, match="blocked claims"):
        PolicyDecision(
            status=PolicyDecisionStatus.ALLOWED,
            reason_code=AdapterFindingCode.ALLOWED,
            rationale="Allowed.",
            blocked_claims=("treatment",),
            evidence=(_evidence("allowed"),),
        )


def test_request_binds_m1803_media_and_unique_source_artifacts() -> None:
    with pytest.raises(ValidationError, match="M18-03"):
        AdaptBiomarkerPanelIntendedUseRequest.model_validate(
            _request().model_dump(mode="python")
            | {"upstream_result": _artifact("wrong", media_type="application/json")}
        )
    source = _artifact("source")
    with pytest.raises(ValidationError, match="source artifact digests"):
        _request(source_artifacts=(source, source))


def test_canonical_request_mapping_is_stable() -> None:
    request = _request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )
    assert result_payload_digest({"result_digest": "sha256:" + "a" * 64}).startswith("sha256:")


def test_result_closure_rejects_each_tamper_shape() -> None:
    result = m1804.M1804Engine().adapt(_request())
    assert result.adapted_object is not None
    adapted_object = result.adapted_object
    cases = (
        {"request_digest": "sha256:" + "b" * 64},
        {"result_id": "result.tampered"},
        {
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            )
        },
        {"status": AdapterStatus.ABSTAINED},
        {
            "status": AdapterStatus.ABSTAINED,
            "adapted_object": None,
            "abstention_reason": "blocked",
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            ),
            "human_review_required": False,
        },
        {"adapted_object": adapted_object.model_copy(update={"object_id": "object.tampered"})},
        {"result_digest": "sha256:" + "c" * 64},
    )
    for update in cases:
        candidate = result.model_copy(update=update)
        with pytest.raises(ValidationError):
            BiomarkerPanelIntendedUseAdapterResult.model_validate(
                candidate.model_dump(mode="python"), strict=True
            )


def test_public_function_and_service_validation_paths() -> None:
    request = _request()
    result = m1804.adapt_biomarker_panel_intended_use(request)
    assert result.status is AdapterStatus.ADAPTED
