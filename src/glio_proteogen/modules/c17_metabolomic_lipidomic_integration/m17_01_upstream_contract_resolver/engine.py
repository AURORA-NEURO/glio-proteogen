"""Replay-safe typed upstream contract resolver for M17-01."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_01 import (
    M1701_EVIDENCE_CLAIM,
    M1701_MODULE_ID,
    CompatibilityDecision,
    CompatibilityReport,
    CompatibilityStatus,
    ResolverFinding,
    ResolverFindingCode,
    ResolverStatus,
    ResolveVariantPeptideUpstreamContractsRequest,
    UpstreamCandidate,
    ValidatedUpstreamBundle,
    VariantPeptideUpstreamResolutionResult,
)
from glio_proteogen.contracts.m17_01.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ResolveVariantPeptideUpstreamContractsRequest)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_CONTROL_STATES: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class M1701AuthorizationError(ValueError):
    """Raised before candidate traversal when a required control is unsafe."""


class M1701ReplayError(ValueError):
    """Raised when a result digest no longer binds to its request payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m1701_authorization(candidate: object) -> None:
    """Check all seven controls before typed candidate traversal."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M1701AuthorizationError("M17-01 requires all seven upstream controls")  # noqa: TRY003
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M1701AuthorizationError(  # noqa: TRY003
                f"M17-01 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M17-01 resolves declared contracts; it does not estimate biology.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Compatibility is sensitive to declared media, version, consent, support, "
            "and intended-use rules.",
        ),
    )


def _control_decisions(
    request: ResolveVariantPeptideUpstreamContractsRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    decisions: list[ControlDecisionRecord] = []
    for role, decision in (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    ):
        decisions.append(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
            )
        )
    decisions.extend(
        (
            ControlDecisionRecord(
                role=ControlRole.IDENTITY_LINEAGE,
                decision_id=refs.identity_lineage.decision_id,
                state=refs.identity_lineage.state.value,
                policy_version=refs.identity_lineage.policy_version,
                evidence_digest=refs.identity_lineage.evidence.digest,
                subject_digest=refs.identity_lineage.binding_digest,
            ),
            ControlDecisionRecord(
                role=ControlRole.CONSENT,
                decision_id=refs.consent.decision_id,
                state=refs.consent.state.value,
                policy_version=refs.consent.policy_version,
                evidence_digest=refs.consent.evidence.digest,
            ),
        )
    )
    return tuple(decisions)


def _provenance(request: ResolveVariantPeptideUpstreamContractsRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1701_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(
            *(candidate.artifact.digest for candidate in request.candidates),
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(
    request: ResolveVariantPeptideUpstreamContractsRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1701_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="contract_resolution_only",
            statement=(
                "This module validates caller-declared upstream compatibility "
                "and does not infer biology."
            ),
        ),
        Limitation(
            code="no_variant_claim",
            statement="The variant-peptide parent remains outside this resolver's output ceiling.",
        ),
        Limitation(
            code="no_identity_inference",
            statement=(
                "Identity, consent, treatment, and upstream evidence "
                "are not inferred or mutated."
            ),
        ),
    )


def _rule_match(
    candidate: UpstreamCandidate, request: ResolveVariantPeptideUpstreamContractsRequest
) -> bool:
    return any(
        rule.required_source_kind is candidate.source_kind
        and rule.required_media_type == candidate.artifact.media_type
        and rule.required_intended_use == candidate.intended_use
        for rule in request.configuration.rules
    )


def _decision_for(
    candidate: UpstreamCandidate,
    request: ResolveVariantPeptideUpstreamContractsRequest,
) -> tuple[CompatibilityDecision, str]:
    evidence = candidate.evidence
    if candidate.compatibility is CompatibilityStatus.UNKNOWN:
        return (
            CompatibilityDecision(
                candidate_id=candidate.candidate_id,
                status=CompatibilityStatus.UNKNOWN,
                reason_code=ResolverFindingCode.COMPATIBILITY_UNKNOWN,
                rationale="Candidate compatibility is unknown and cannot be promoted.",
                evidence=evidence,
            ),
            "unresolved",
        )
    if candidate.compatibility is CompatibilityStatus.INCOMPATIBLE:
        return (
            CompatibilityDecision(
                candidate_id=candidate.candidate_id,
                status=CompatibilityStatus.INCOMPATIBLE,
                reason_code=ResolverFindingCode.INCOMPATIBLE_VERSION,
                rationale=candidate.compatibility_reason,
                evidence=evidence,
            ),
            "rejected",
        )
    if not _rule_match(candidate, request):
        code = ResolverFindingCode.MEDIA_TYPE_MISMATCH
        rationale = "No configured source-kind, media-type, and intended-use rule matched."
    elif candidate.consent_state is not ConsentState.GRANTED:
        code = ResolverFindingCode.CONSENT_NOT_GRANTED
        rationale = "Candidate consent is not granted by its owning authority."
    elif candidate.support_status is not SupportStatus.SUPPORTED:
        code = ResolverFindingCode.SUPPORT_NOT_AVAILABLE
        rationale = "Candidate support status is not supported."
    elif candidate.provenance_artifact is None:
        code = ResolverFindingCode.PROVENANCE_MISSING
        rationale = "Candidate has no provenance artifact."
    elif candidate.intended_use not in request.configuration.accepted_intended_uses:
        code = ResolverFindingCode.INTENDED_USE_MISMATCH
        rationale = "Candidate intended use is not accepted by configuration."
    else:
        return (
            CompatibilityDecision(
                candidate_id=candidate.candidate_id,
                status=CompatibilityStatus.COMPATIBLE,
                reason_code=ResolverFindingCode.ACCEPTED,
                rationale="Candidate satisfies configured compatibility and safety controls.",
                evidence=evidence,
            ),
            "selected",
        )
    return (
        CompatibilityDecision(
            candidate_id=candidate.candidate_id,
            status=CompatibilityStatus.INCOMPATIBLE,
            reason_code=code,
            rationale=rationale,
            evidence=evidence,
        ),
        "rejected",
    )


class M1701Engine:
    """Resolve declared upstream candidates without traversing raw artifacts."""

    def validate_request(self, candidate: object) -> ResolveVariantPeptideUpstreamContractsRequest:
        preflight_m1701_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def resolve(self, candidate: object) -> VariantPeptideUpstreamResolutionResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        decisions: list[CompatibilityDecision] = []
        selected: list[UpstreamCandidate] = []
        rejected: list[str] = []
        unresolved: list[str] = []
        for item in request.candidates:
            decision, bucket = _decision_for(item, request)
            decisions.append(decision)
            if bucket == "selected":
                selected.append(item)
            elif bucket == "unresolved":
                unresolved.append(item.candidate_id)
            else:
                rejected.append(item.candidate_id)
        report = CompatibilityReport(
            report_id=f"report.{request.request_id}",
            version="0.1.0-provisional",
            decisions=tuple(decisions),
            selected_candidate_ids=tuple(item.candidate_id for item in selected),
            rejected_candidate_ids=tuple(rejected),
            unresolved_candidate_ids=tuple(unresolved),
            evidence=_evidence(request),
        )
        findings = tuple(
            ResolverFinding(
                finding_id=f"finding.{request.request_id}.{decision.candidate_id}",
                code=decision.reason_code,
                message=decision.rationale,
                evidence=decision.evidence,
            )
            for decision in decisions
            if decision.status is not CompatibilityStatus.COMPATIBLE
        )
        if selected:
            bundle = ValidatedUpstreamBundle(
                bundle_id=f"bundle.{request.request_id}",
                version="0.1.0-provisional",
                candidates=tuple(selected),
                compatibility_report=report,
                evidence=_evidence(request),
            )
            status = ResolverStatus.VALIDATED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="compatible_upstream",
                rationale=(
                    "At least one upstream candidate satisfies the configured "
                    "compatibility rules."
                ),
            )
            abstention_reason = None
        else:
            bundle = None
            status = ResolverStatus.ABSTAINED
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="no_compatible_upstream",
                rationale=(
                    "No upstream candidate can be promoted without violating "
                    "compatibility or safety controls."
                ),
            )
            abstention_reason = "No compatible, consented, supported upstream candidate was found."
        payload: dict[str, Any] = {
            "output_type": "variant_peptide_upstream_resolution",
            "result_id": f"result.{request.request_id}",
            "result_version": "0.1.0-provisional",
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "bundle": bundle,
            "compatibility_report": report,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "variant peptide",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": bool(unresolved) or not selected,
        }
        payload["result_digest"] = result_payload_digest(
            VariantPeptideUpstreamResolutionResult.model_construct(**payload)
        )
        return VariantPeptideUpstreamResolutionResult.model_validate(payload, strict=True)

    def replay(
        self,
        result: VariantPeptideUpstreamResolutionResult,
    ) -> VariantPeptideUpstreamResolutionResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M1701ReplayError("M17-01 result request digest mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M1701ReplayError("M17-01 result payload digest mismatch")  # noqa: TRY003
        return result


def resolve_variant_peptide_upstream_contracts(
    candidate: object,
) -> VariantPeptideUpstreamResolutionResult:
    return M1701Engine().resolve(candidate)


__all__ = [
    "M1701AuthorizationError",
    "M1701Engine",
    "M1701ReplayError",
    "preflight_m1701_authorization",
    "resolve_variant_peptide_upstream_contracts",
]
