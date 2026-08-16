"""Deterministic, replay-safe M19-01 upstream contract resolution.

The engine only evaluates caller-declared metadata.  It never opens an
artifact, infers consent or identity, mutates evidence, or turns unknown
support into a negative biological claim.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_01 import (
    M1901_CONTRACT_VERSION,
    M1901_EVIDENCE_CLAIM,
    M1901_MODULE_ID,
    CompatibilityDecision,
    CompatibilityReport,
    CompatibilityStatus,
    ProteotypeUpstreamResolutionResult,
    ResolveProteotypeUpstreamContractsRequest,
    ResolverFinding,
    ResolverFindingCode,
    ResolverStatus,
    UpstreamCandidate,
    ValidatedUpstreamBundle,
)
from glio_proteogen.contracts.m19_01.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(ResolveProteotypeUpstreamContractsRequest)
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


class M1901AuthorizationError(ValueError):
    """Raised before candidate traversal when a required control is unsafe."""


class M1901ReplayError(ValueError):
    """Raised when a result digest no longer binds to its exact payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m1901_authorization(candidate: object) -> None:
    """Check all seven controls before strict typed candidate traversal."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M1901AuthorizationError("M19-01 requires all seven upstream controls")
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M1901AuthorizationError(
                f"M19-01 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M19-01 resolves declared contracts; it does not estimate biology.",
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
            "provenance, and intended-use rules.",
        ),
    )


def _control_decisions(
    request: ResolveProteotypeUpstreamContractsRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    ordered = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=decision.state.value,
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, decision in ordered
    )


def _provenance(request: ResolveProteotypeUpstreamContractsRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1901_MODULE_ID,
        module_version=M1901_CONTRACT_VERSION,
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
    request: ResolveProteotypeUpstreamContractsRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1901_EVIDENCE_CLAIM)
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
            code="no_proteotype_claim",
            statement="The parent proteotype remains outside this resolver's output ceiling.",
        ),
        Limitation(
            code="no_identity_inference",
            statement=(
                "Identity, consent, treatment, and upstream evidence are not inferred or mutated."
            ),
        ),
    )


def _rule_match(
    candidate: UpstreamCandidate,
    request: ResolveProteotypeUpstreamContractsRequest,
) -> bool:
    return any(
        rule.required_source_kind is candidate.source_kind
        and rule.required_media_type == candidate.artifact.media_type
        and rule.required_intended_use == candidate.intended_use
        for rule in request.configuration.rules
    )


def _decision_for(
    candidate: UpstreamCandidate,
    request: ResolveProteotypeUpstreamContractsRequest,
) -> tuple[CompatibilityDecision, str]:
    if candidate.compatibility is CompatibilityStatus.UNKNOWN:
        return (
            CompatibilityDecision(
                candidate_id=candidate.candidate_id,
                status=CompatibilityStatus.UNKNOWN,
                reason_code=ResolverFindingCode.COMPATIBILITY_UNKNOWN,
                rationale="Candidate compatibility is unknown and cannot be promoted.",
                evidence=candidate.evidence,
            ),
            "unresolved",
        )
    if candidate.compatibility is CompatibilityStatus.INCOMPATIBLE:
        return (
            CompatibilityDecision(
                candidate_id=candidate.candidate_id,
                status=CompatibilityStatus.INCOMPATIBLE,
                reason_code=ResolverFindingCode.INCOMPATIBLE,
                rationale=candidate.compatibility_reason,
                evidence=candidate.evidence,
            ),
            "rejected",
        )
    checks: tuple[tuple[bool, ResolverFindingCode, str], ...] = (
        (
            _rule_match(candidate, request),
            ResolverFindingCode.MEDIA_TYPE_MISMATCH,
            "No configured source-kind, media-type, and intended-use rule matched.",
        ),
        (
            candidate.consent_state is ConsentState.GRANTED,
            ResolverFindingCode.CONSENT_NOT_GRANTED,
            "Candidate consent is not granted by its owning authority.",
        ),
        (
            candidate.support_status is SupportStatus.SUPPORTED,
            ResolverFindingCode.SUPPORT_NOT_AVAILABLE,
            "Candidate support status is not supported.",
        ),
        (
            candidate.provenance_artifact is not None,
            ResolverFindingCode.PROVENANCE_MISSING,
            "Candidate has no provenance artifact.",
        ),
        (
            candidate.intended_use in request.configuration.accepted_intended_uses,
            ResolverFindingCode.INTENDED_USE_MISMATCH,
            "Candidate intended use is not accepted by configuration.",
        ),
    )
    for passed, code, rationale in checks:
        if not passed:
            return (
                CompatibilityDecision(
                    candidate_id=candidate.candidate_id,
                    status=CompatibilityStatus.INCOMPATIBLE,
                    reason_code=code,
                    rationale=rationale,
                    evidence=candidate.evidence,
                ),
                "rejected",
            )
    return (
        CompatibilityDecision(
            candidate_id=candidate.candidate_id,
            status=CompatibilityStatus.COMPATIBLE,
            reason_code=ResolverFindingCode.COMPATIBLE_ACCEPTED,
            rationale="Candidate satisfies configured compatibility and safety controls.",
            evidence=candidate.evidence,
        ),
        "selected",
    )


class M1901Engine:
    """Resolve declared upstream candidates without traversing raw artifacts."""

    def validate_request(
        self,
        candidate: object,
    ) -> ResolveProteotypeUpstreamContractsRequest:
        preflight_m1901_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def resolve(self, candidate: object) -> ProteotypeUpstreamResolutionResult:
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
            version=M1901_CONTRACT_VERSION,
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
        can_validate = bool(selected) and not unresolved
        bundle = (
            ValidatedUpstreamBundle(
                bundle_id=f"bundle.{request.request_id}",
                version=M1901_CONTRACT_VERSION,
                candidates=tuple(selected),
                compatibility_report=report,
                evidence=_evidence(request),
            )
            if can_validate
            else None
        )
        status = ResolverStatus.VALIDATED if can_validate else ResolverStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED if can_validate else SupportStatus.REVIEW_REQUIRED,
            reason_code="compatible_upstream" if can_validate else "upstream_review_required",
            rationale=(
                "All promoted upstream candidates satisfy compatibility and safety controls."
                if can_validate
                else "Unresolved or unsupported upstream inputs require safe review before promotion."
            ),
        )
        abstention_reason = (
            None
            if can_validate
            else "No fully resolved, consented, supported upstream candidate was found."
        )
        payload: dict[str, Any] = {
            "output_type": "proteotype_upstream_resolution",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M1901_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "bundle": bundle,
            "compatibility_report": report,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": not can_validate,
        }
        payload["result_digest"] = result_payload_digest(
            ProteotypeUpstreamResolutionResult.model_construct(**payload)
        )
        return ProteotypeUpstreamResolutionResult.model_validate(payload, strict=True)

    def replay(
        self,
        result: ProteotypeUpstreamResolutionResult,
    ) -> ProteotypeUpstreamResolutionResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M1901ReplayError("M19-01 result request digest mismatch")
        if result.result_id != f"result.{result.request_digest.removeprefix('sha256:')}":
            raise M1901ReplayError("M19-01 result identifier mismatch")
        if result.result_digest != result_payload_digest(result):
            raise M1901ReplayError("M19-01 result payload digest mismatch")
        return result


def resolve_proteotype_upstream_contracts(
    candidate: object,
) -> ProteotypeUpstreamResolutionResult:
    """Resolve one strict request through the M19-01 engine."""

    return M1901Engine().resolve(candidate)


__all__ = [
    "M1901AuthorizationError",
    "M1901Engine",
    "M1901ReplayError",
    "preflight_m1901_authorization",
    "resolve_proteotype_upstream_contracts",
]
