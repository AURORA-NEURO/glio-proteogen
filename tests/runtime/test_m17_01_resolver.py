"""Runtime and adversarial coverage for the provisional M17-01 resolver."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m17_01 import (
    CompatibilityRule,
    CompatibilityStatus,
    ResolverConfiguration,
    ResolverFindingCode,
    ResolveVariantPeptideUpstreamContractsRequest,
    UpstreamCandidate,
    UpstreamSourceKind,
)
from glio_proteogen.contracts.m17_01.canonical import result_payload_digest
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
    m17_01_upstream_contract_resolver as m1701,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    digest = sha256_digest(f"artifact:{name}:{media_type}")
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{name}",
        version="1.0.0",
        digest=digest,
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Synthetic caller-declared evidence for M17-01 tests.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context(
    *, identity_state: IdentityLineageState = IdentityLineageState.RESOLVED
) -> ExecutionContext:
    artifacts = {
        role: _artifact(role)
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended_use",
            "consent",
        )
    }
    return ExecutionContext(
        request_id="request.synthetic.m1701",
        actor_id="actor.synthetic.m1701",
        occurred_at=datetime(2026, 8, 15, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=identity_state,
                policy_version="1.0.0",
                binding_digest=sha256_digest("synthetic.identity.binding"),
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
        rationale="Synthetic contract fixture does not estimate biology.",
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


def _candidate(
    candidate_id: str,
    *,
    compatibility: CompatibilityStatus,
    source_kind: UpstreamSourceKind = UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
    media_type: str = "application/vnd.ms.proteome+json",
    intended_use: str = "variant_peptide_upstream",
) -> UpstreamCandidate:
    artifact = _artifact(candidate_id, media_type)
    return UpstreamCandidate(
        candidate_id=candidate_id,
        source_kind=source_kind,
        artifact=artifact,
        compatibility=compatibility,
        compatibility_reason=f"Synthetic compatibility declaration: {compatibility.value}.",
        consent_state=(
            ConsentState.GRANTED
            if compatibility is CompatibilityStatus.COMPATIBLE
            else ConsentState.UNKNOWN
        ),
        intended_use=intended_use,
        support_status=(
            SupportStatus.SUPPORTED
            if compatibility is CompatibilityStatus.COMPATIBLE
            else SupportStatus.REVIEW_REQUIRED
        ),
        provenance_artifact=(artifact if compatibility is CompatibilityStatus.COMPATIBLE else None),
        uncertainty=_uncertainty(),
        evidence=(_evidence(artifact),),
    )


def _request(
    *candidates: UpstreamCandidate,
) -> ResolveVariantPeptideUpstreamContractsRequest:
    source = _artifact("source", "application/vnd.m17.source+json")
    configuration = ResolverConfiguration(
        configuration_id="config.synthetic.m1701",
        version="1.0.0",
        rules=(
            CompatibilityRule(
                rule_id="rule.proteome",
                name="proteome upstream",
                required_source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
                required_media_type="application/vnd.ms.proteome+json",
                required_intended_use="variant_peptide_upstream",
                evidence=(_evidence(source),),
            ),
        ),
        accepted_intended_uses=("variant_peptide_upstream",),
        evidence=(_evidence(source),),
    )
    return ResolveVariantPeptideUpstreamContractsRequest(
        request_id="request.synthetic.m1701",
        context=_context(),
        candidates=tuple(candidates),
        configuration=configuration,
        source_artifacts=(source,),
    )


def test_mixed_candidates_preserve_selection_rejection_and_unknown() -> None:
    request = _request(
        _candidate("candidate.accepted", compatibility=CompatibilityStatus.COMPATIBLE),
        _candidate("candidate.rejected", compatibility=CompatibilityStatus.INCOMPATIBLE),
        _candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),
    )

    result = m1701.M1701Engine().resolve(request)

    assert result.status.value == "validated"
    assert result.bundle is not None
    assert result.compatibility_report.selected_candidate_ids == ("candidate.accepted",)
    assert result.compatibility_report.rejected_candidate_ids == ("candidate.rejected",)
    assert result.compatibility_report.unresolved_candidate_ids == ("candidate.unknown",)
    assert {finding.code for finding in result.findings} == {
        ResolverFindingCode.INCOMPATIBLE_VERSION,
        ResolverFindingCode.COMPATIBILITY_UNKNOWN,
    }
    assert result.human_review_required is True
    assert m1701.M1701Engine().replay(result) == result


def test_no_compatible_candidate_abstains_without_negative_conversion() -> None:
    result = m1701.M1701Engine().resolve(
        _request(_candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN))
    )

    assert result.status.value == "abstained"
    assert result.bundle is None
    assert result.abstention_reason
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.compatibility_report.selected_candidate_ids == ()
    assert result.human_review_required is True


def test_preflight_rejects_unresolved_identity_before_resolution() -> None:
    request = _request(
        _candidate("candidate.accepted", compatibility=CompatibilityStatus.COMPATIBLE)
    ).model_copy(update={"context": _context(identity_state=IdentityLineageState.UNRESOLVED)})

    with pytest.raises(m1701.M1701AuthorizationError, match="identity_lineage"):
        m1701.M1701Engine().resolve(request)


def test_replay_rejects_tampered_result_payload() -> None:
    request = _request(
        _candidate("candidate.accepted", compatibility=CompatibilityStatus.COMPATIBLE)
    )
    result = m1701.M1701Engine().resolve(request)
    tampered = result.model_copy(update={"human_review_required": True})
    tampered = tampered.model_copy(update={"result_digest": result.result_digest})

    with pytest.raises(m1701.M1701ReplayError, match="payload digest"):
        m1701.M1701Engine().replay(tampered)


def test_replay_rejects_self_rehashed_semantic_mutation() -> None:
    result = m1701.M1701Engine().resolve(
        _request(_candidate("candidate.accepted", compatibility=CompatibilityStatus.COMPATIBLE))
    )
    tampered = result.model_copy(update={"human_review_required": True})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises(m1701.M1701ReplayError, match="semantic replay"):
        m1701.M1701Engine().replay(tampered)
