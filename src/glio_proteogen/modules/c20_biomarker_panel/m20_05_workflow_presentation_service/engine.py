"""Deterministic, replay-safe M20-05 human-review workspace presentation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_05 import (
    M2005_CONTRACT_VERSION,
    M2005_MAX_EVIDENCE,
    M2005_MODULE_ID,
    HumanReviewWorkspace,
    PresentProteinSubtypeHumanReviewWorkspaceRequest,
    ProteinSubtypeHumanReviewWorkspaceResult,
    ReviewItemStatus,
    WorkflowFinding,
    WorkflowFindingCode,
    WorkspaceStatus,
)
from glio_proteogen.contracts.m20_05.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(PresentProteinSubtypeHumanReviewWorkspaceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeHumanReviewWorkspaceResult)
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


class M2005AuthorizationError(ValueError):
    """Raised before presentation when a required control is unsafe."""

    def __init__(self, message: str = "M20-05 requires all seven upstream controls") -> None:
        super().__init__(message)


class M2005ReplayError(ValueError):
    """Raised when a result no longer binds to its request or payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m2005_authorization(candidate: object) -> None:
    """Require all seven caller-declared controls before reading review items."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        if references is None:
            raise M2005AuthorizationError  # noqa: TRY301
        for name, expected in _CONTROL_STATES.items():
            decision = _member(references, name)
            actual = _member(decision, "state")
            actual_value = getattr(actual, "value", actual)
            if actual_value != expected:
                raise M2005AuthorizationError(  # noqa: TRY301, TRY003
                    f"M20-05 control {name} must be {expected}; received {actual_value}"
                )
    except M2005AuthorizationError:
        raise
    except Exception as error:
        raise M2005AuthorizationError from error


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M20-05 presents caller-declared evidence and does not estimate biological truth."
        ),
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
            "Interpretation is sensitive to the locked policy, upstream support, view ordering, "
            "reviewer context and provisional ABI.",
        ),
    )


def _control_decisions(
    request: PresentProteinSubtypeHumanReviewWorkspaceRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
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


def _provenance(
    request: PresentProteinSubtypeHumanReviewWorkspaceRequest,
) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        dict.fromkeys(
            (
                request.aligned_evidence_bundle.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                request.policy.configuration.model_reference.digest,
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M2005_MODULE_ID,
        module_version=M2005_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.policy.configuration.model_dump(mode="json")),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(
    request: PresentProteinSubtypeHumanReviewWorkspaceRequest,
) -> tuple[EvidenceReference, ...]:
    candidates: list[EvidenceReference] = [
        EvidenceReference(
            reference=request.aligned_evidence_bundle,
            role="evidence",
            claim="Caller-declared M20-04 aligned evidence bundle.",
        ),
        *(
            EvidenceReference(
                reference=artifact,
                role="evidence",
                claim="Caller-declared M20-05 workflow presentation evidence.",
            )
            for artifact in request.source_artifacts
        ),
        EvidenceReference(
            reference=request.policy.configuration.model_reference,
            role="evidence",
            claim="Locked caller-declared presentation model reference.",
        ),
        *(evidence for item in request.review_items for evidence in item.evidence),
    ]
    selected: list[EvidenceReference] = []
    seen: set[str] = set()
    for evidence in candidates:
        if evidence.reference.digest not in seen and len(selected) < M2005_MAX_EVIDENCE:
            selected.append(evidence)
            seen.add(evidence.reference.digest)
    return tuple(selected)


def _findings(
    request: PresentProteinSubtypeHumanReviewWorkspaceRequest,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[WorkflowFinding, ...]:
    findings: list[WorkflowFinding] = []
    for item in request.review_items:
        if item.status in {ReviewItemStatus.CONFLICTED, ReviewItemStatus.UNRESOLVED}:
            findings.append(
                WorkflowFinding(
                    finding_id=f"finding.{request.request_id}.{item.item_id}.review",
                    code=WorkflowFindingCode.DISCREPANCY_REQUIRES_REVIEW,
                    message=(
                        f"Review item {item.item_id} retains a declared discrepancy and requires "
                        "human adjudication."
                    ),
                    evidence=evidence,
                )
            )
        if item.status is ReviewItemStatus.ABSTAINED:
            findings.append(
                WorkflowFinding(
                    finding_id=f"finding.{request.request_id}.{item.item_id}.abstained",
                    code=WorkflowFindingCode.AUTOMATION_BIAS_GUARD,
                    message=(
                        f"Review item {item.item_id} is explicitly abstained; no presentation "
                        "claim is emitted for that item."
                    ),
                    evidence=evidence,
                )
            )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="caller_declared_workspace",
            statement=(
                "Review items, evidence summaries, uncertainty, provenance and ordering are "
                "caller-declared and not issuer-authenticated."
            ),
        ),
        Limitation(
            code="upstream_not_recomputed",
            statement=(
                "M20-05 binds the M20-04 aligned evidence artifact and does not recompute or "
                "authenticate upstream biology."
            ),
        ),
        Limitation(
            code="human_review_only",
            statement=(
                "The workspace supports human review and emits no protein-subtype conclusion, "
                "kinase state, treatment recommendation or identity inference."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement=(
                "The ABI remains provisional pending owner confirmation and release governance."
            ),
        ),
    )


def _workspace(
    request: PresentProteinSubtypeHumanReviewWorkspaceRequest,
    evidence: tuple[EvidenceReference, ...],
) -> HumanReviewWorkspace:
    return HumanReviewWorkspace(
        workspace_id=f"workspace.{request.request_id}",
        version=request.policy.configuration.version,
        items=request.review_items,
        ordering=request.policy.default_ordering,
        automation_bias_warning=(
            "Review evidence, uncertainty and provenance before accepting any machine-suggested "
            "ordering or next action."
        ),
        source_bundle=request.aligned_evidence_bundle,
        evidence=evidence,
    )


class M2005Engine:
    """Present one bounded M20-04-aligned workspace with exact replay."""

    def validate_request(
        self, candidate: object
    ) -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
        preflight_m2005_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def present(self, candidate: object) -> ProteinSubtypeHumanReviewWorkspaceResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        findings = _findings(request, evidence)
        item_abstained = any(
            item.status is ReviewItemStatus.ABSTAINED for item in request.review_items
        )
        workspace = None if item_abstained else _workspace(request, evidence)
        status = WorkspaceStatus.ABSTAINED if item_abstained else WorkspaceStatus.PRESENTED
        support = SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED if item_abstained else SupportStatus.SUPPORTED,
            reason_code=(
                "workflow_item_abstained" if item_abstained else "supported_review_workspace"
            ),
            rationale=(
                "At least one caller-declared item is abstained; no workspace claim is emitted."
                if item_abstained
                else "All required controls and presentation fields are present for human review."
            ),
        )
        payload: dict[str, Any] = {
            "output_type": "protein_subtype_human_review_workspace",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M2005_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "workspace": workspace,
            "findings": findings,
            "abstention_reason": (
                "M20-05 abstained because a caller-declared review item is explicitly abstained."
                if item_abstained
                else None
            ),
            "parent_target": "protein subtype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": True,
        }
        payload["result_digest"] = result_payload_digest(
            ProteinSubtypeHumanReviewWorkspaceResult.model_construct(**payload)
        )
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(
        self,
        result: ProteinSubtypeHumanReviewWorkspaceResult,
    ) -> ProteinSubtypeHumanReviewWorkspaceResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2005ReplayError("M20-05 result request digest mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2005ReplayError("M20-05 result payload digest mismatch")  # noqa: TRY003
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        expected = self.present(validated.request)
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            raise M2005ReplayError("M20-05 result semantic replay mismatch")  # noqa: TRY003
        return validated


def present_protein_subtype_human_review_workspace(
    candidate: object,
) -> ProteinSubtypeHumanReviewWorkspaceResult:
    return M2005Engine().present(candidate)


__all__ = [
    "M2005AuthorizationError",
    "M2005Engine",
    "M2005ReplayError",
    "preflight_m2005_authorization",
    "present_protein_subtype_human_review_workspace",
]
