"""Adversarial closure tests for the M20-01 resolver contract.

The tests intentionally exercise the negative space of the contract: every
candidate outcome is classified, status buckets agree with reason codes,
content-addressed evidence remains unique, and replay identities cannot be
edited without validation failing closed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m20_01 import (
    M2001_MODULE_ID,
    CompatibilityDecision,
    CompatibilityReport,
    CompatibilityRule,
    CompatibilityStatus,
    ProteinSubtypeUpstreamResolutionResult,
    ResolveProteinSubtypeUpstreamContractsRequest,
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
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m20_01_upstream_contract_resolver as m2001,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)
_MEDIA_TYPE = "application/vnd.glio-proteogen.source+json"
_INTENDED_USE = "protein subtype export"


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m2001": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="M20-01 caller-declared upstream compatibility evidence",
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


def _context(*, request_id: str = "request.m2001") -> ExecutionContext:
    accepted = UpstreamDecisionState.ACCEPTED
    return ExecutionContext(
        request_id=request_id,
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
    consent_state: ConsentState = ConsentState.GRANTED,
    support_status: SupportStatus = SupportStatus.SUPPORTED,
    provenance: bool = True,
) -> UpstreamCandidate:
    return UpstreamCandidate(
        candidate_id=candidate_id,
        source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
        artifact=_artifact(candidate_id, media_type=_MEDIA_TYPE),
        compatibility=compatibility,
        compatibility_reason="Candidate declaration is compatible under the locked policy.",
        consent_state=consent_state,
        intended_use=_INTENDED_USE,
        support_status=support_status,
        provenance_artifact=_artifact(f"{candidate_id}.provenance") if provenance else None,
        uncertainty=_uncertainty(),
        evidence=(_evidence(f"{candidate_id}.evidence"),),
    )


def _rule(rule_id: str = "rule.proteome") -> CompatibilityRule:
    return CompatibilityRule(
        rule_id=rule_id,
        name="Biomarker-panel translation compatibility",
        required_source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
        required_media_type=_MEDIA_TYPE,
        required_intended_use=_INTENDED_USE,
        evidence=(_evidence(f"{rule_id}.evidence"),),
    )


def _configuration() -> ResolverConfiguration:
    return ResolverConfiguration(
        configuration_id="configuration.m2001",
        version="1.0.0",
        rules=(_rule(),),
        accepted_intended_uses=(_INTENDED_USE,),
        evidence=(_evidence("configuration.evidence"),),
    )


def _request(
    candidates: tuple[UpstreamCandidate, ...] = (_candidate(),),
    *,
    context_request_id: str = "request.m2001",
) -> ResolveProteinSubtypeUpstreamContractsRequest:
    return ResolveProteinSubtypeUpstreamContractsRequest(
        request_id="request.m2001",
        context=_context(request_id=context_request_id),
        candidates=candidates,
        configuration=_configuration(),
        source_artifacts=(_artifact("source.proteome"), _artifact("source.genome")),
    )


def _decision(
    candidate_id: str = "candidate.proteome",
    *,
    status: CompatibilityStatus = CompatibilityStatus.COMPATIBLE,
    reason_code: ResolverFindingCode = ResolverFindingCode.COMPATIBLE_ACCEPTED,
) -> CompatibilityDecision:
    return CompatibilityDecision(
        candidate_id=candidate_id,
        status=status,
        reason_code=reason_code,
        rationale="Candidate is classified under the locked compatibility policy.",
        evidence=(_evidence(f"{candidate_id}.decision"),),
    )


def _report(
    decision: CompatibilityDecision | None = None,
    *,
    selected: tuple[str, ...] = ("candidate.proteome",),
    rejected: tuple[str, ...] = (),
    unresolved: tuple[str, ...] = (),
) -> CompatibilityReport:
    return CompatibilityReport(
        report_id="report.m2001",
        version="1.0.0",
        decisions=(decision or _decision(),),
        selected_candidate_ids=selected,
        rejected_candidate_ids=rejected,
        unresolved_candidate_ids=unresolved,
        evidence=(_evidence("report.evidence"),),
    )


def _provenance(request: ResolveProteinSubtypeUpstreamContractsRequest) -> ProvenanceRecord:
    refs = request.context.references
    decisions = (
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
    return ProvenanceRecord(
        activity_id="activity.m2001",
        actor_id=request.context.actor_id,
        module_id=M2001_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=_WHEN,
        input_digests=tuple(item.digest for item in request.source_artifacts),
        configuration_digest=sha256_digest(request.configuration.model_dump(mode="json")),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _result(
    request: ResolveProteinSubtypeUpstreamContractsRequest,
    report: CompatibilityReport,
    *,
    status: ResolverStatus = ResolverStatus.VALIDATED,
) -> ProteinSubtypeUpstreamResolutionResult:
    bundle = (
        ValidatedUpstreamBundle(
            bundle_id="bundle.m2001",
            version="1.0.0",
            candidates=(request.candidates[0],),
            compatibility_report=report,
            evidence=(_evidence("bundle.evidence"),),
        )
        if status is ResolverStatus.VALIDATED
        else None
    )
    finding = ResolverFinding(
        finding_id="finding.m2001",
        code=(
            ResolverFindingCode.COMPATIBLE_ACCEPTED
            if status is ResolverStatus.VALIDATED
            else ResolverFindingCode.COMPATIBILITY_UNKNOWN
        ),
        message="Resolver outcome is explicitly classified.",
        evidence=(_evidence("finding.evidence"),),
    )
    payload: dict[str, Any] = {
        "output_type": "protein_subtype_upstream_resolution",
        "result_id": "result.pending",
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "result_digest": "sha256:" + "0" * 64,
        "request": request,
        "status": status,
        "bundle": bundle,
        "compatibility_report": report,
        "findings": (finding,),
        "abstention_reason": (
            None if status is ResolverStatus.VALIDATED else "Compatibility is unresolved."
        ),
        "parent_target": "protein subtype",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=(
                SupportStatus.SUPPORTED
                if status is ResolverStatus.VALIDATED
                else SupportStatus.REVIEW_REQUIRED
            ),
            reason_code="accepted" if status is ResolverStatus.VALIDATED else "review",
            rationale="Typed support state is preserved.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request),
        "evidence": (_evidence("result.evidence"),),
        "limitations": (
            Limitation(code="caller_declared", statement="Upstream authority is external."),
        ),
        "human_review_required": status is ResolverStatus.ABSTAINED,
    }
    payload["result_id"] = f"result.{payload['request_digest'].removeprefix('sha256:')}"
    payload["result_digest"] = result_payload_digest(
        ProteinSubtypeUpstreamResolutionResult.model_construct(**payload)
    )
    return ProteinSubtypeUpstreamResolutionResult.model_validate(payload, strict=True)


def test_candidate_and_evidence_references_are_content_addressed_and_unique() -> None:
    with pytest.raises(ValidationError, match="granted consent"):
        _candidate(consent_state=ConsentState.UNKNOWN)
    with pytest.raises(ValidationError, match="supported status"):
        _candidate(support_status=SupportStatus.REVIEW_REQUIRED)
    with pytest.raises(ValidationError, match="provenance evidence"):
        _candidate(provenance=False)
    with pytest.raises(ValidationError, match="artifact and provenance digests"):
        UpstreamCandidate.model_validate(
            _candidate().model_dump(mode="python") | {"provenance_artifact": _candidate().artifact}
        )
    duplicate_evidence = _evidence("duplicate")
    with pytest.raises(ValidationError, match="candidate evidence digests"):
        UpstreamCandidate.model_validate(
            _candidate().model_dump(mode="python")
            | {"evidence": (duplicate_evidence, duplicate_evidence)}
        )
    with pytest.raises(ValidationError, match="rule evidence digests"):
        CompatibilityRule.model_validate(
            _rule().model_dump(mode="python")
            | {"evidence": (duplicate_evidence, duplicate_evidence)}
        )
    duplicate_evidence = _evidence("decision.duplicate")
    with pytest.raises(ValidationError, match="decision evidence digests"):
        CompatibilityDecision.model_validate(
            _decision().model_dump(mode="python")
            | {"evidence": (duplicate_evidence, duplicate_evidence)}
        )


def test_decision_reason_codes_and_report_buckets_cannot_disagree() -> None:
    with pytest.raises(ValidationError, match="reason code"):
        _decision(
            status=CompatibilityStatus.INCOMPATIBLE,
            reason_code=ResolverFindingCode.COMPATIBLE_ACCEPTED,
        )
    with pytest.raises(ValidationError, match="selected candidates"):
        CompatibilityReport.model_validate(
            _report().model_dump(mode="python")
            | {
                "decisions": (
                    _decision(
                        status=CompatibilityStatus.INCOMPATIBLE,
                        reason_code=ResolverFindingCode.INCOMPATIBLE,
                    ),
                ),
            }
        )
    unknown = _decision(
        "candidate.unknown",
        status=CompatibilityStatus.UNKNOWN,
        reason_code=ResolverFindingCode.COMPATIBILITY_UNKNOWN,
    )
    report = _report(unknown, selected=(), unresolved=("candidate.unknown",))
    assert report.selected_candidate_ids == ()
    with pytest.raises(ValidationError, match="classify every"):
        CompatibilityReport.model_validate(
            report.model_dump(mode="python") | {"unresolved_candidate_ids": ()}
        )


def test_configuration_and_request_closure_reject_duplicates_and_mismatches() -> None:
    with pytest.raises(ValidationError, match="rule ids"):
        ResolverConfiguration.model_validate(
            _configuration().model_dump(mode="python") | {"rules": (_rule(), _rule())}
        )
    with pytest.raises(ValidationError, match="accepted intended uses"):
        ResolverConfiguration.model_validate(
            _configuration().model_dump(mode="python")
            | {"accepted_intended_uses": (_INTENDED_USE, _INTENDED_USE)}
        )
    with pytest.raises(ValidationError, match="every compatibility rule"):
        ResolverConfiguration.model_validate(
            _configuration().model_dump(mode="python") | {"accepted_intended_uses": ("other use",)}
        )
    duplicate_evidence = _evidence("config.duplicate")
    with pytest.raises(ValidationError, match="configuration evidence digests"):
        ResolverConfiguration.model_validate(
            _configuration().model_dump(mode="python")
            | {"evidence": (duplicate_evidence, duplicate_evidence)}
        )
    with pytest.raises(ValidationError, match="context request id"):
        ResolveProteinSubtypeUpstreamContractsRequest.model_validate(
            _request(context_request_id="request.other").model_dump(mode="python")
        )
    duplicate_source = _artifact("source.duplicate")
    duplicate_digest = duplicate_source.model_copy(
        update={"artifact_id": "artifact.source.digest-duplicate"}
    )
    with pytest.raises(ValidationError, match="source artifact digests"):
        ResolveProteinSubtypeUpstreamContractsRequest.model_validate(
            _request().model_dump(mode="python")
            | {"source_artifacts": (duplicate_source, duplicate_digest)}
        )
    duplicate_id = _artifact("source.other").model_copy(
        update={"artifact_id": duplicate_source.artifact_id}
    )
    with pytest.raises(ValidationError, match="source artifact ids"):
        ResolveProteinSubtypeUpstreamContractsRequest.model_validate(
            _request().model_dump(mode="python")
            | {"source_artifacts": (duplicate_source, duplicate_id)}
        )
    with pytest.raises(ValidationError, match="candidate ids"):
        ResolveProteinSubtypeUpstreamContractsRequest.model_validate(
            _request(candidates=(_candidate(), _candidate())).model_dump(mode="python")
        )


def test_report_bundle_and_result_closure_reject_nested_tampering() -> None:
    report = _report()
    with pytest.raises(ValidationError, match="decision candidate ids"):
        CompatibilityReport.model_validate(
            report.model_dump(mode="python") | {"decisions": (_decision(), _decision())}
        )
    with pytest.raises(ValidationError, match="mutually exclusive"):
        CompatibilityReport.model_validate(
            report.model_dump(mode="python") | {"rejected_candidate_ids": ("candidate.proteome",)}
        )
    duplicate_evidence = _evidence("report.duplicate")
    with pytest.raises(ValidationError, match="report evidence digests"):
        CompatibilityReport.model_validate(
            report.model_dump(mode="python")
            | {"evidence": (duplicate_evidence, duplicate_evidence)}
        )

    with pytest.raises(ValidationError, match="validated candidate ids"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.duplicate",
            version="1.0.0",
            candidates=(_candidate(), _candidate()),
            compatibility_report=report,
            evidence=(_evidence("bundle.duplicate"),),
        )
    with pytest.raises(ValidationError, match="cannot include incompatible"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.incompatible",
            version="1.0.0",
            candidates=(_candidate(compatibility=CompatibilityStatus.INCOMPATIBLE),),
            compatibility_report=report,
            evidence=(_evidence("bundle.incompatible"),),
        )
    mismatch = _report(
        _decision("candidate.other"),
        selected=("candidate.other",),
    )
    with pytest.raises(ValidationError, match="match selected"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.mismatch",
            version="1.0.0",
            candidates=(_candidate(),),
            compatibility_report=mismatch,
            evidence=(_evidence("bundle.mismatch"),),
        )


def test_bundle_requires_selected_consent_version_and_unique_evidence() -> None:
    report = _report()
    with pytest.raises(ValidationError, match="granted consent"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.bad-consent",
            version="1.0.0",
            candidates=(_candidate(consent_state=ConsentState.UNKNOWN),),
            compatibility_report=report,
            evidence=(_evidence("bundle.bad-consent"),),
        )
    with pytest.raises(ValidationError, match="version"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.bad-version",
            version="2.0.0",
            candidates=(_candidate(),),
            compatibility_report=report,
            evidence=(_evidence("bundle.bad-version"),),
        )
    evidence = _evidence("bundle.duplicate-evidence")
    with pytest.raises(ValidationError, match="bundle evidence digests"):
        ValidatedUpstreamBundle(
            bundle_id="bundle.duplicate-evidence",
            version="1.0.0",
            candidates=(_candidate(),),
            compatibility_report=report,
            evidence=(evidence, evidence),
        )


def test_result_identity_replay_and_safe_abstention_are_closed() -> None:
    request = _request()
    result = _result(request, _report())
    assert result.result_id == f"result.{result.request_digest.removeprefix('sha256:')}"
    assert result_payload_digest(result) == result.result_digest
    with pytest.raises(ValidationError, match="identifier"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            result.model_copy(update={"result_id": "result.tampered"})
        )
    with pytest.raises(ValidationError, match="request digest"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
        )
    with pytest.raises(ValidationError, match="provenance"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            result.model_copy(
                update={
                    "provenance": result.provenance.model_copy(
                        update={"module_id": "GLIO-PROTEOGEN-M19-01"}
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="finding ids"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            result.model_copy(update={"findings": (result.findings[0], result.findings[0])})
        )
    duplicate_evidence = result.evidence[0]
    with pytest.raises(ValidationError, match="result evidence digests"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            result.model_copy(update={"evidence": (duplicate_evidence, duplicate_evidence)})
        )
    with pytest.raises(ValidationError, match="result digest"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
        )
    with pytest.raises(ValidationError, match="supported upstream"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            result.model_copy(
                update={
                    "support_decision": SupportDecision(
                        status=SupportStatus.REVIEW_REQUIRED,
                        reason_code="review",
                        rationale="Forced review.",
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="human review"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            result.model_copy(update={"human_review_required": True})
        )
    unknown = _candidate(
        "candidate.unknown",
        compatibility=CompatibilityStatus.UNKNOWN,
        support_status=SupportStatus.REVIEW_REQUIRED,
    )
    unknown_request = _request((unknown,))
    unknown_report = _report(
        _decision(
            "candidate.unknown",
            status=CompatibilityStatus.UNKNOWN,
            reason_code=ResolverFindingCode.COMPATIBILITY_UNKNOWN,
        ),
        selected=(),
        unresolved=("candidate.unknown",),
    )
    abstained = _result(unknown_request, unknown_report, status=ResolverStatus.ABSTAINED)
    with pytest.raises(ValidationError, match="abstained result requires"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            abstained.model_copy(update={"bundle": result.bundle})
        )
    with pytest.raises(ValidationError, match="human review"):
        ProteinSubtypeUpstreamResolutionResult.model_validate(
            abstained.model_copy(update={"human_review_required": False})
        )


def test_provenance_covers_nested_candidate_and_rule_evidence() -> None:
    request = _request()
    result = m2001.M2001Engine().resolve(request)
    nested_digests = {
        *(candidate.artifact.digest for candidate in request.candidates),
        *(
            candidate.provenance_artifact.digest
            for candidate in request.candidates
            if candidate.provenance_artifact is not None
        ),
        *(artifact.digest for artifact in request.source_artifacts),
        *(item.reference.digest for item in request.configuration.evidence),
        *(item.reference.digest for rule in request.configuration.rules for item in rule.evidence),
        *(item.reference.digest for candidate in request.candidates for item in candidate.evidence),
    }
    assert nested_digests <= set(result.provenance.input_digests)
