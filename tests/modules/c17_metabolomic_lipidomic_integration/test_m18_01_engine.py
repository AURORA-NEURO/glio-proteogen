"""Runtime, preflight, and replay tests for M18-01."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m18_01 import (
    CompatibilityRule,
    CompatibilityStatus,
    ResolveBiomarkerPanelUpstreamContractsRequest,
    ResolverConfiguration,
    UpstreamCandidate,
    UpstreamSourceKind,
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
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m18_01_upstream_contract_resolver import (  # noqa: E501
    M1801AuthorizationError,
    M1801Engine,
    M1801ReplayError,
    M1801Service,
    preflight_m1801_authorization,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)
_MEDIA_TYPE = "application/vnd.glio-proteogen.source+json"
_INTENDED_USE = "biomarker panel export"
_CONTROL_COUNT = 7


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1801": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="M18-01 runtime evidence",
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Contract resolution does not estimate biology.",
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
        request_id="request.m1801.runtime",
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


def _candidate(
    candidate_id: str = "candidate.proteome",
    *,
    compatibility: CompatibilityStatus = CompatibilityStatus.COMPATIBLE,
    source_media_type: str = _MEDIA_TYPE,
) -> UpstreamCandidate:
    return UpstreamCandidate(
        candidate_id=candidate_id,
        source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
        artifact=_artifact(candidate_id, media_type=source_media_type),
        compatibility=compatibility,
        compatibility_reason="Caller-declared compatibility state.",
        consent_state=ConsentState.GRANTED,
        intended_use=_INTENDED_USE,
        support_status=SupportStatus.SUPPORTED,
        provenance_artifact=_artifact(f"{candidate_id}.provenance"),
        uncertainty=_uncertainty(),
        evidence=(_evidence(candidate_id),),
    )


def _request(
    candidates: tuple[UpstreamCandidate, ...] | None = None,
) -> ResolveBiomarkerPanelUpstreamContractsRequest:
    rule = CompatibilityRule(
        rule_id="rule.proteome",
        name="Spatial proteomics source compatibility",
        required_source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
        required_media_type=_MEDIA_TYPE,
        required_intended_use=_INTENDED_USE,
        evidence=(_evidence("rule"),),
    )
    configuration = ResolverConfiguration(
        configuration_id="configuration.m1801.runtime",
        version="1.0.0",
        rules=(rule,),
        accepted_intended_uses=(_INTENDED_USE,),
        evidence=(_evidence("configuration"),),
    )
    return ResolveBiomarkerPanelUpstreamContractsRequest(
        request_id="request.m1801.runtime",
        context=_context(),
        candidates=tuple(candidates or (_candidate(),)),
        configuration=configuration,
        source_artifacts=(_artifact("source.proteome"), _artifact("source.ptm")),
    )


def test_supported_candidate_is_validated_with_complete_uncertainty_and_controls() -> None:
    result = M1801Engine().resolve(_request())
    assert result.status.value == "validated"
    assert result.bundle is not None
    assert result.bundle.compatibility_report.selected_candidate_ids == ("candidate.proteome",)
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.human_review_required is False
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.uncertainty.measurement.state is EstimateState.NOT_ESTIMABLE


def test_unknown_and_incompatible_candidates_abstain_without_negative_inference() -> None:
    for compatibility in (CompatibilityStatus.UNKNOWN, CompatibilityStatus.INCOMPATIBLE):
        result = M1801Engine().resolve(_request((_candidate(compatibility=compatibility),)))
        assert result.status.value == "abstained"
        assert result.bundle is None
        assert result.human_review_required is True
        assert result.compatibility_report.selected_candidate_ids == ()
        assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_media_mismatch_is_rejected_and_mixed_unknown_requires_review() -> None:
    mismatch = _candidate("candidate.mismatch", source_media_type="application/octet-stream")
    unknown = _candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN)
    result = M1801Engine().resolve(_request((_candidate(), mismatch, unknown)))
    assert result.status.value == "validated"
    assert result.bundle is not None
    assert result.compatibility_report.rejected_candidate_ids == ("candidate.mismatch",)
    assert result.compatibility_report.unresolved_candidate_ids == ("candidate.unknown",)
    assert result.human_review_required is True


def test_preflight_rejects_missing_or_denied_controls_before_validation() -> None:
    with pytest.raises(M1801AuthorizationError, match="all seven"):
        preflight_m1801_authorization({})
    payload = _request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = ConsentState.UNKNOWN
    with pytest.raises(M1801AuthorizationError, match="consent"):
        preflight_m1801_authorization(payload)


def test_service_replay_accepts_exact_result_and_rejects_request_or_payload_tamper() -> None:
    service = M1801Service()
    result = service.resolve(_request())
    assert service.replay(result) == result
    with pytest.raises(M1801ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "0" * 64}))
    with pytest.raises(M1801ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"human_review_required": True}))


def test_strict_request_adapter_rejects_non_model_candidate_mapping() -> None:
    payload = _request().model_dump(mode="json")
    payload["candidates"][0]["artifact"]["digest"] = "not-a-digest"
    with pytest.raises(ValidationError):
        M1801Engine().resolve(payload)
