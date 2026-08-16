"""Adversarial contract closure tests for provisional M19-01."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_01 import (
    CompatibilityDecision,
    CompatibilityReport,
    CompatibilityRule,
    CompatibilityStatus,
    ProteotypeUpstreamResolutionResult,
    ResolveProteotypeUpstreamContractsRequest,
    ResolverConfiguration,
    ResolverFinding,
    ResolverFindingCode,
    ResolverStatus,
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
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)
_MEDIA_TYPE = "application/vnd.glio-proteogen.source+json"
_INTENDED_USE = "proteotype export"


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1901": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="M19-01 caller-declared upstream compatibility evidence",
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
        sensitivity_notes=("Typed compatibility uncertainty remains visible.",),
    )


def _context() -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id="request.m1901",
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
        name="Immunopeptidomic proteome compatibility",
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
    provenance: bool = True,
) -> UpstreamCandidate:
    return UpstreamCandidate(
        candidate_id=candidate_id,
        source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
        artifact=_artifact(candidate_id, media_type=_MEDIA_TYPE),
        compatibility=compatibility,
        compatibility_reason="Caller-declared compatibility state.",
        consent_state=consent_state,
        intended_use=_INTENDED_USE,
        support_status=support_status,
        provenance_artifact=_artifact(f"{candidate_id}.provenance") if provenance else None,
        uncertainty=_uncertainty(),
        evidence=(_evidence(candidate_id), _evidence(f"{candidate_id}.provenance"))
        if provenance
        else (_evidence(candidate_id),),
    )


def _configuration() -> ResolverConfiguration:
    return ResolverConfiguration(
        configuration_id="configuration.m1901",
        version="1.0.0",
        rules=(_rule(),),
        accepted_intended_uses=(_INTENDED_USE,),
        evidence=(_evidence("configuration"),),
    )


def _request(
    candidates: tuple[UpstreamCandidate, ...] = (_candidate(),),
) -> ResolveProteotypeUpstreamContractsRequest:
    source_artifacts = [
        _artifact("source.proteome"),
        _artifact("source.ptm"),
        *(candidate.artifact for candidate in candidates),
        *(
            candidate.provenance_artifact
            for candidate in candidates
            if candidate.provenance_artifact is not None
        ),
        *(evidence.reference for candidate in candidates for evidence in candidate.evidence),
        *(evidence.reference for rule in _configuration().rules for evidence in rule.evidence),
        *(evidence.reference for evidence in _configuration().evidence),
    ]
    unique_source_artifacts = tuple(
        {artifact.digest: artifact for artifact in source_artifacts}.values()
    )
    return ResolveProteotypeUpstreamContractsRequest(
        request_id="request.m1901",
        context=_context(),
        candidates=candidates,
        configuration=_configuration(),
        source_artifacts=unique_source_artifacts,
    )


def _decision(
    candidate_id: str = "candidate.proteome",
    status: CompatibilityStatus = CompatibilityStatus.COMPATIBLE,
) -> CompatibilityDecision:
    code = {
        CompatibilityStatus.COMPATIBLE: ResolverFindingCode.COMPATIBLE_ACCEPTED,
        CompatibilityStatus.INCOMPATIBLE: ResolverFindingCode.INCOMPATIBLE_VERSION,
        CompatibilityStatus.UNKNOWN: ResolverFindingCode.COMPATIBILITY_UNKNOWN,
    }[status]
    return CompatibilityDecision(
        candidate_id=candidate_id,
        status=status,
        reason_code=code,
        rationale="Contract test decision.",
        evidence=(_evidence(f"decision.{candidate_id}"),),
    )


def _report(
    decisions: tuple[CompatibilityDecision, ...] = (_decision(),),
) -> CompatibilityReport:
    return CompatibilityReport(
        report_id="report.m1901",
        version="1.0.0",
        decisions=decisions,
        selected_candidate_ids=tuple(
            item.candidate_id for item in decisions if item.status is CompatibilityStatus.COMPATIBLE
        ),
        rejected_candidate_ids=tuple(
            item.candidate_id
            for item in decisions
            if item.status is CompatibilityStatus.INCOMPATIBLE
        ),
        unresolved_candidate_ids=tuple(
            item.candidate_id for item in decisions if item.status is CompatibilityStatus.UNKNOWN
        ),
        evidence=(_evidence("report"),),
    )


def _control_records() -> tuple[ControlDecisionRecord, ...]:
    refs = _context().references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )


def _provenance(request: ResolveProteotypeUpstreamContractsRequest) -> ProvenanceRecord:
    return ProvenanceRecord(
        activity_id="activity.m1901",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M19-01",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(request.candidates[0].artifact.digest,),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=_control_records(),
    )


def _validated_result() -> ProteotypeUpstreamResolutionResult:
    request = _request()
    report = _report()
    bundle = ValidatedUpstreamBundle(
        bundle_id="bundle.m1901",
        version="1.0.0",
        candidates=request.candidates,
        compatibility_report=report,
        evidence=(_evidence("bundle"),),
    )
    provisional = ProteotypeUpstreamResolutionResult.model_construct(
        result_id=f"result.{canonical_request_digest(request).removeprefix('sha256:')}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "a" * 64,
        request=request,
        status=ResolverStatus.VALIDATED,
        bundle=bundle,
        compatibility_report=report,
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="supported_upstream",
            rationale="All selected upstream candidates satisfy the locked contract.",
        ),
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=(_evidence("result"),),
        limitations=(
            Limitation(
                code="provisional_abi",
                statement="The M19-01 ABI remains provisional pending owner confirmation.",
            ),
        ),
    )
    digest = result_payload_digest(provisional)
    return ProteotypeUpstreamResolutionResult.model_validate(
        provisional.model_copy(update={"result_digest": digest}).model_dump(mode="python")
    )


def test_compatible_candidates_require_consent_support_and_provenance() -> None:
    with pytest.raises(ValidationError, match="granted consent"):
        _candidate(consent_state=ConsentState.UNKNOWN)
    with pytest.raises(ValidationError, match="supported status"):
        _candidate(support_status=SupportStatus.REVIEW_REQUIRED)
    with pytest.raises(ValidationError, match="provenance evidence"):
        _candidate(provenance=False)


def test_configuration_and_request_close_duplicate_and_context_ids() -> None:
    with pytest.raises(ValidationError, match="rule ids"):
        ResolverConfiguration.model_validate(
            _configuration().model_dump(mode="python") | {"rules": (_rule(), _rule())}
        )
    with pytest.raises(ValidationError, match="accepted intended uses"):
        ResolverConfiguration.model_validate(
            _configuration().model_dump(mode="python")
            | {"accepted_intended_uses": (_INTENDED_USE, _INTENDED_USE)}
        )
    with pytest.raises(ValidationError, match="request candidate ids"):
        ResolveProteotypeUpstreamContractsRequest.model_validate(
            _request(candidates=(_candidate(), _candidate())).model_dump(mode="python")
        )
    with pytest.raises(ValidationError, match="context request id"):
        ResolveProteotypeUpstreamContractsRequest.model_validate(
            _request().model_dump(mode="python")
            | {"context": _context().model_copy(update={"request_id": "other"})}
        )


def test_decision_reason_and_report_buckets_are_typed_and_closed() -> None:
    with pytest.raises(ValidationError, match="reason code"):
        CompatibilityDecision.model_validate(
            _decision().model_dump(mode="python")
            | {"reason_code": ResolverFindingCode.INCOMPATIBLE_VERSION}
        )
    unknown = _decision("candidate.unknown", CompatibilityStatus.UNKNOWN)
    incompatible = _decision("candidate.incompatible", CompatibilityStatus.INCOMPATIBLE)
    report = _report((_decision(), unknown, incompatible))
    assert report.selected_candidate_ids == ("candidate.proteome",)
    assert report.rejected_candidate_ids == ("candidate.incompatible",)
    assert report.unresolved_candidate_ids == ("candidate.unknown",)
    with pytest.raises(ValidationError, match="classify every"):
        CompatibilityReport.model_validate(
            report.model_dump(mode="python") | {"selected_candidate_ids": ()}
        )


def test_report_allows_empty_selection_but_bundle_never_does() -> None:
    unknown = _decision("candidate.unknown", CompatibilityStatus.UNKNOWN)
    report = _report((unknown,))
    assert report.selected_candidate_ids == ()
    with pytest.raises(ValidationError, match="cannot include incompatible"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.bad",
            version="1.0.0",
            candidates=(_candidate(compatibility=CompatibilityStatus.INCOMPATIBLE),),
            compatibility_report=report,
            evidence=(_evidence("bundle.bad"),),
        )


def test_result_digest_identity_and_abstention_closure_are_fail_closed() -> None:
    result = _validated_result()
    assert result.result_id.removeprefix("result.") == result.request_digest.removeprefix("sha256:")
    assert result_payload_digest(result) == result.result_digest
    with pytest.raises(ValidationError, match="request digest"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
        )
    with pytest.raises(ValidationError, match="identifier"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_copy(update={"result_id": "result.tampered"})
        )
    with pytest.raises(ValidationError, match="result digest"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
        )


def test_result_findings_are_unique_and_provenance_is_owned_by_m1901() -> None:
    result = _validated_result()
    finding = ResolverFinding(
        finding_id="finding.one",
        code=ResolverFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        message="Owner confirmation remains pending.",
    )
    with pytest.raises(ValidationError, match="finding ids"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_dump(mode="python") | {"findings": (finding, finding)}
        )
    with pytest.raises(ValidationError, match="provenance"):
        ProteotypeUpstreamResolutionResult.model_validate(
            result.model_dump(mode="python")
            | {
                "provenance": result.provenance.model_copy(
                    update={"module_id": "GLIO-PROTEOGEN-M19-02"}
                )
            }
        )


def test_canonical_request_mapping_is_stable_and_no_unknown_fields_are_coerced() -> None:
    request = _request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )
    with pytest.raises(ValidationError):
        ResolveProteotypeUpstreamContractsRequest.model_validate(
            request.model_dump(mode="python") | {"unexpected": True}
        )
