"""Deterministic, replay-safe M19-02 cross-source reconciliation.

The engine compares caller-declared alignment observations only.  It never
opens source artifacts, infers identity or consent, mutates upstream evidence,
or converts an unsupported/missing observation into a negative finding.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_02 import (
    M1902_CONTRACT_VERSION,
    M1902_EVIDENCE_CLAIM,
    M1902_MODULE_ID,
    AlignedEvidenceBundle,
    AlignmentFinding,
    AlignmentFindingCode,
    AlignmentObservationStatus,
    AlignmentStatus,
    AlignProteotypeSourcesRequest,
    DiscrepancySeverity,
    ProteotypeAlignmentResult,
)
from glio_proteogen.contracts.m19_02.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(AlignProteotypeSourcesRequest)
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


class M1902AuthorizationError(ValueError):
    """Raised before source traversal when a required control is unsafe."""


class M1902ReplayError(ValueError):
    """Raised when a result no longer binds to its exact request or payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m1902_authorization(request: object) -> None:
    """Check all seven caller-declared controls before typed traversal."""

    references = _member(_member(request, "context"), "references")
    if references is None:
        raise M1902AuthorizationError(  # noqa: TRY003
            "M19-02 requires all seven upstream controls"
        )
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M1902AuthorizationError(  # noqa: TRY003
                f"M19-02 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Alignment reconciliation does not estimate a biological probability.",
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
            "Sensitivity is limited by declared source coverage, assay support, and context.",
        ),
    )


def _control_decisions(
    request: AlignProteotypeSourcesRequest,
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
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, decision in ordered
    )


def _provenance(request: AlignProteotypeSourcesRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1902_MODULE_ID,
        module_version=M1902_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: AlignProteotypeSourcesRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1902_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="caller_declared_alignment",
            statement=(
                "M19-02 compares caller-declared source metadata and does not "
                "traverse raw artifacts."
            ),
        ),
        Limitation(
            code="conflict_preserved",
            statement=(
                "Disagreement is emitted as a discrepancy map and is never relabeled or erased."
            ),
        ),
        Limitation(
            code="no_prohibited_outputs",
            statement=(
                "Kinase activity, generic all-omics fusion, treatment recommendations, "
                "and identity inference "
                "remain outside this module's output ceiling."
            ),
        ),
    )


def _bundle(request: AlignProteotypeSourcesRequest) -> AlignedEvidenceBundle:
    return AlignedEvidenceBundle(
        bundle_id=f"bundle.{request.request_id}",
        version=M1902_CONTRACT_VERSION,
        source_artifacts=request.source_artifacts,
        observations=request.observations,
        discrepancies=request.discrepancies,
        configuration=request.configuration,
        evidence=_evidence(request),
    )


def _finding_code(
    status: AlignmentObservationStatus, severity: DiscrepancySeverity | None
) -> AlignmentFindingCode:
    if severity is DiscrepancySeverity.CRITICAL:
        return AlignmentFindingCode.BIOLOGICAL_CONFLICT_REVIEW
    if status is AlignmentObservationStatus.CONFLICTED:
        return AlignmentFindingCode.DIMENSION_CONFLICT
    return AlignmentFindingCode.INPUT_INCOMPLETE


def _findings(request: AlignProteotypeSourcesRequest) -> tuple[AlignmentFinding, ...]:
    discrepancy_by_dimension = {item.dimension: item for item in request.discrepancies}
    findings: list[AlignmentFinding] = []
    for observation in request.observations:
        discrepancy = discrepancy_by_dimension.get(observation.dimension)
        if observation.status is AlignmentObservationStatus.ALIGNED:
            continue
        severity = discrepancy.severity if discrepancy is not None else None
        evidence = discrepancy.evidence if discrepancy is not None else observation.evidence
        findings.append(
            AlignmentFinding(
                finding_id=f"finding.{request.request_id}.{observation.dimension.value}",
                code=_finding_code(observation.status, severity),
                message=(
                    discrepancy.description if discrepancy is not None else observation.rationale
                ),
                evidence=evidence,
            )
        )
    return tuple(findings)


class M1902Engine:
    """Reconcile declared source dimensions without traversing raw evidence."""

    def validate_request(self, candidate: object) -> AlignProteotypeSourcesRequest:
        preflight_m1902_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def align(self, candidate: object) -> ProteotypeAlignmentResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        has_non_aligned = any(
            observation.status is not AlignmentObservationStatus.ALIGNED
            for observation in request.observations
        )
        requires_review = any(item.review_required for item in request.discrepancies)
        can_align = not has_non_aligned and not requires_review
        bundle = _bundle(request) if can_align else None
        findings = () if can_align else _findings(request)
        status = AlignmentStatus.ALIGNED if can_align else AlignmentStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED if can_align else SupportStatus.REVIEW_REQUIRED,
            reason_code="aligned_sources" if can_align else "alignment_review_required",
            rationale=(
                "All seven source dimensions agree under the locked configuration."
                if can_align
                else "One or more source dimensions are unresolved and require safe review."
            ),
        )
        payload: dict[str, Any] = {
            "output_type": "proteotype_alignment",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M1902_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "aligned_bundle": bundle,
            "findings": findings,
            "abstention_reason": (
                None
                if can_align
                else "Cross-source alignment is not fully supported; discrepancies remain explicit."
            ),
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": not can_align,
        }
        payload["result_digest"] = result_payload_digest(
            ProteotypeAlignmentResult.model_construct(**payload)
        )
        return ProteotypeAlignmentResult.model_validate(payload, strict=True)

    def replay(self, result: ProteotypeAlignmentResult) -> ProteotypeAlignmentResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M1902ReplayError("M19-02 result request digest mismatch")  # noqa: TRY003
        if result.result_id != f"result.{result.request_digest.removeprefix('sha256:')}":
            raise M1902ReplayError("M19-02 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M1902ReplayError("M19-02 result payload digest mismatch")  # noqa: TRY003
        try:
            return ProteotypeAlignmentResult.model_validate(
                result.model_dump(mode="python"), strict=True
            )
        except ValueError as exc:
            raise M1902ReplayError("M19-02 result validation failed") from exc  # noqa: TRY003


def align_proteotype_sources(candidate: object) -> ProteotypeAlignmentResult:
    """Align one strict request through the M19-02 engine."""

    return M1902Engine().align(candidate)


__all__ = [
    "M1902AuthorizationError",
    "M1902Engine",
    "M1902ReplayError",
    "align_proteotype_sources",
    "preflight_m1902_authorization",
]
