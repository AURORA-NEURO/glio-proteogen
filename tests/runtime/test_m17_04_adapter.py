"""Runtime and adversarial coverage for the provisional M17-04 adapter."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m17_04 import (
    AdapterFindingCode,
    AdaptVariantPeptideIntendedUseRequest,
    ClaimCeiling,
    DisplaySemantics,
    IntendedUseKind,
    IntendedUseRegistration,
    PolicyDecisionStatus,
)
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
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_04_intended_use_adapter as m1704,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m1704:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Synthetic caller-declared M17-04 policy evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
    artifacts = {role: _artifact(role) for role in (
        "configuration", "identity", "provenance", "quality", "support", "intended_use", "consent"
    )}
    return ExecutionContext(
        request_id="request.synthetic.m1704",
        actor_id="actor.synthetic.m1704",
        occurred_at=datetime(2026, 8, 15, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m1704.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Synthetic policy fixture does not estimate biology.",
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


def _registration(
    *,
    intended_use: IntendedUseKind = IntendedUseKind.RESEARCH,
    audience: str = "research",
    evidence_tier: int = 1,
    maximum_claim: str = "bounded evidence summary",
    sections: tuple[str, ...] = (
        "support",
        "uncertainty",
        "provenance",
        "evidence",
        "limitations",
    ),
) -> IntendedUseRegistration:
    artifact = _artifact("registration")
    evidence = (_evidence(artifact),)
    return IntendedUseRegistration(
        registration_id="registration.synthetic.m1704",
        version="1.0.0",
        intended_use=intended_use,
        audience=audience,
        evidence_tier=evidence_tier,
        claim_ceiling=ClaimCeiling(
            maximum_claim=maximum_claim,
            prohibited_interpretations=("kinase activity", "treatment recommendation"),
            rationale="Synthetic bounded claim ceiling.",
            evidence=evidence,
        ),
        display_semantics=DisplaySemantics(
            section_order=sections,
            safe_default="show uncertainty and support before claims",
            evidence=evidence,
        ),
        evidence=evidence,
    )


def _request(**registration_kwargs: object) -> AdaptVariantPeptideIntendedUseRequest:
    upstream = _artifact("upstream", "application/vnd.glio-proteogen.m17-03+json")
    source = _artifact("source", "application/vnd.m17.source+json")
    return AdaptVariantPeptideIntendedUseRequest(
        request_id="request.synthetic.m1704",
        context=_context(),
        upstream_result=upstream,
        registration=_registration(**registration_kwargs),
        source_artifacts=(source,),
    )


def test_registered_research_use_adapts_and_replays() -> None:
    result = m1704.M1704Engine().adapt(_request())

    assert result.status.value == "adapted"
    assert result.adapted_object is not None
    assert result.policy_decision.status is PolicyDecisionStatus.ALLOWED
    assert result.parent_target == "variant peptide"
    assert result.emits_parent is False
    assert result.human_review_required is False
    assert m1704.M1704Engine().replay(result) == result


def test_treatment_claim_abstains_without_object() -> None:
    result = m1704.M1704Engine().adapt(
        _request(maximum_claim="direct treatment recommendation")
    )

    assert result.status.value == "abstained"
    assert result.adapted_object is None
    assert result.policy_decision.status is PolicyDecisionStatus.BLOCKED
    assert result.findings[0].code is AdapterFindingCode.TREATMENT_RECOMMENDATION_BLOCKED
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.human_review_required is True


def test_clinical_review_requires_review_but_preserves_bounded_object() -> None:
    result = m1704.M1704Engine().adapt(
        _request(
            intended_use=IntendedUseKind.CLINICAL_REVIEW,
            audience="clinical_review_board",
            evidence_tier=3,
        )
    )

    assert result.status.value == "adapted"
    assert result.adapted_object is not None
    assert result.policy_decision.status is PolicyDecisionStatus.REVIEW_REQUIRED
    assert result.human_review_required is True


def test_incomplete_display_semantics_abstains() -> None:
    result = m1704.M1704Engine().adapt(_request(sections=("evidence",)))

    assert result.status.value == "abstained"
    assert result.findings[0].code is AdapterFindingCode.DISPLAY_SEMANTICS_INCOMPLETE


def test_unsupported_audience_abstains() -> None:
    result = m1704.M1704Engine().adapt(_request(audience="unregistered_audience"))

    assert result.status.value == "abstained"
    assert any(
        finding.code is AdapterFindingCode.AUDIENCE_UNSUPPORTED
        for finding in result.findings
    )


def test_control_denial_precedes_policy_traversal() -> None:
    request = _request().model_copy(
        update={
            "context": _context().model_copy(
                update={
                    "references": _context().references.model_copy(
                        update={
                            "consent": _context().references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )

    with pytest.raises(m1704.M1704AuthorizationError, match="consent"):
        m1704.M1704Engine().adapt(request)


def test_tampered_result_digest_is_rejected() -> None:
    result = m1704.M1704Engine().adapt(_request())
    tampered = result.model_copy(update={"human_review_required": True})

    with pytest.raises(m1704.M1704ReplayError, match="payload digest"):
        m1704.M1704Engine().replay(tampered)
