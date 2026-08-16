"""Adversarial contract closure tests for provisional M18-01."""

# ruff: noqa: PLR0913

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m18_01 import (
    CompatibilityDecision,
    CompatibilityReport,
    CompatibilityRule,
    CompatibilityStatus,
    ResolveBiomarkerPanelUpstreamContractsRequest,
    ResolverConfiguration,
    ResolverFindingCode,
    UpstreamCandidate,
    UpstreamSourceKind,
    ValidatedUpstreamBundle,
    canonical_request_digest,
    result_payload_digest,
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

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)
_MEDIA_TYPE = "application/vnd.glio-proteogen.source+json"
_INTENDED_USE = "biomarker panel export"


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
        claim="M18-01 caller-declared upstream compatibility evidence",
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Compatibility resolution does not estimate biology.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Media, consent, support, and intended-use rules remain explicit.",),
    )


def _context() -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id="request.m1801",
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


def _rule(rule_id: str = "rule.proteome") -> CompatibilityRule:
    return CompatibilityRule(
        rule_id=rule_id,
        name="Spatial proteomics source compatibility",
        required_source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
        required_media_type=_MEDIA_TYPE,
        required_intended_use=_INTENDED_USE,
        evidence=(_evidence(rule_id),),
    )


def _candidate(
    candidate_id: str = "candidate.proteome",
    *,
    compatibility: CompatibilityStatus = CompatibilityStatus.COMPATIBLE,
    consent_state: ConsentState = ConsentState.GRANTED,
    support_status: SupportStatus = SupportStatus.SUPPORTED,
    intended_use: str = _INTENDED_USE,
    provenance: bool = True,
) -> UpstreamCandidate:
    return UpstreamCandidate(
        candidate_id=candidate_id,
        source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
        artifact=_artifact(candidate_id, media_type=_MEDIA_TYPE),
        compatibility=compatibility,
        compatibility_reason="Candidate declaration is compatible under the locked policy.",
        consent_state=consent_state,
        intended_use=intended_use,
        support_status=support_status,
        provenance_artifact=_artifact(f"{candidate_id}.provenance") if provenance else None,
        uncertainty=_uncertainty(),
        evidence=(_evidence(candidate_id),),
    )


def _configuration() -> ResolverConfiguration:
    return ResolverConfiguration(
        configuration_id="configuration.m1801",
        version="1.0.0",
        rules=(_rule(),),
        accepted_intended_uses=(_INTENDED_USE,),
        evidence=(_evidence("configuration"),),
    )


def _request(
    candidates: tuple[UpstreamCandidate, ...] = (_candidate(),),
) -> ResolveBiomarkerPanelUpstreamContractsRequest:
    return ResolveBiomarkerPanelUpstreamContractsRequest(
        request_id="request.m1801",
        context=_context(),
        candidates=candidates,
        configuration=_configuration(),
        source_artifacts=(_artifact("proteome"), _artifact("genome"), _artifact("ptm")),
    )


def _decision(candidate_id: str = "candidate.proteome") -> CompatibilityDecision:
    return CompatibilityDecision(
        candidate_id=candidate_id,
        status=CompatibilityStatus.COMPATIBLE,
        reason_code=ResolverFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        rationale="Candidate is compatible for contract testing.",
        evidence=(_evidence(candidate_id),),
    )


def _report() -> CompatibilityReport:
    return CompatibilityReport(
        report_id="report.m1801",
        version="1.0.0",
        decisions=(_decision(),),
        selected_candidate_ids=("candidate.proteome",),
        evidence=(_evidence("report"),),
    )


def test_compatible_candidates_require_consent_support_and_provenance() -> None:
    with pytest.raises(ValidationError, match="granted consent"):
        _candidate(consent_state=ConsentState.UNKNOWN)
    with pytest.raises(ValidationError, match="supported status"):
        _candidate(support_status=SupportStatus.REVIEW_REQUIRED)
    with pytest.raises(ValidationError, match="provenance evidence"):
        _candidate(provenance=False)


def test_configuration_and_request_candidate_ids_are_unique() -> None:
    with pytest.raises(ValidationError, match="rule ids"):
        ResolverConfiguration.model_validate(
            _configuration().model_dump(mode="python") | {"rules": (_rule(), _rule())}
        )
    with pytest.raises(ValidationError, match="request candidate ids"):
        ResolveBiomarkerPanelUpstreamContractsRequest.model_validate(
            _request(candidates=(_candidate(), _candidate())).model_dump(mode="python")
        )


def test_report_outcomes_are_mutually_exclusive_and_classify_every_decision() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        CompatibilityReport.model_validate(
            _report().model_dump(mode="python")
            | {"rejected_candidate_ids": ("candidate.proteome",)}
        )
    unknown_decision = CompatibilityDecision(
        candidate_id="candidate.unknown",
        status=CompatibilityStatus.UNKNOWN,
        reason_code=ResolverFindingCode.COMPATIBILITY_UNKNOWN,
        rationale="Compatibility evidence is unresolved.",
        evidence=(_evidence("candidate.unknown"),),
    )
    with pytest.raises(ValidationError, match="classify every"):
        CompatibilityReport.model_validate(
            _report().model_dump(mode="python") | {"decisions": (_decision(), unknown_decision)}
        )


def test_bundle_requires_selected_compatible_candidate_membership() -> None:
    with pytest.raises(ValidationError, match="cannot include incompatible"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.m1801",
            version="1.0.0",
            candidates=(_candidate(compatibility=CompatibilityStatus.INCOMPATIBLE),),
            compatibility_report=_report(),
            evidence=(_evidence("bundle"),),
        )
    rejected_decision = CompatibilityDecision(
        candidate_id="candidate.proteome",
        status=CompatibilityStatus.INCOMPATIBLE,
        reason_code=ResolverFindingCode.INCOMPATIBLE_VERSION,
        rationale="Candidate is outside the locked compatibility range.",
        evidence=(_evidence("candidate.proteome.rejected"),),
    )
    selected_decision = _decision("candidate.other")
    mismatch_report = CompatibilityReport(
        report_id="report.m1801.mismatch",
        version="1.0.0",
        decisions=(rejected_decision, selected_decision),
        selected_candidate_ids=("candidate.other",),
        rejected_candidate_ids=("candidate.proteome",),
        evidence=(_evidence("report.mismatch"),),
    )
    with pytest.raises(ValidationError, match="match selected"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.m1801",
            version="1.0.0",
            candidates=(_candidate(),),
            compatibility_report=mismatch_report,
            evidence=(_evidence("bundle"),),
        )


def test_canonical_request_mapping_is_stable() -> None:
    request = _request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )
    assert result_payload_digest({"result_digest": "sha256:" + "a" * 64}).startswith("sha256:")
