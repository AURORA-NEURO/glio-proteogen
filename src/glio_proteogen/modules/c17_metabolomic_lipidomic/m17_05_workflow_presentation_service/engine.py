"""Deterministic authorization-first M17-05 workflow presentation engine."""

# Audit-oriented branches are intentionally explicit.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_05 import (
    M1705_CONTRACT_VERSION,
    M1705_MODULE_ID,
    HumanReviewWorkspace,
    OrderingPolicy,
    PresentVariantPeptideHumanReviewWorkspaceRequest,
    ReviewItem,
    ReviewItemStatus,
    VariantPeptideHumanReviewWorkspaceResult,
    ViewKind,
    WorkflowFinding,
    WorkflowFindingCode,
    WorkspaceStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(PresentVariantPeptideHumanReviewWorkspaceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideHumanReviewWorkspaceResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1705AuthorizationError(PermissionError):
    """Caller controls do not authorize workflow presentation."""

    def __init__(self) -> None:
        super().__init__(
            "M17-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1705ReplayVerificationError(ValueError):
    """An M17-05 result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M17-05 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1705_authorization(candidate: object) -> None:
    """Check all seven caller-declared controls before reading review material."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001
        raise M1705AuthorizationError from None
    if states != expected:
        raise M1705AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1705_authorization(candidate)
    return candidate


def _evidence(
    request: PresentVariantPeptideHumanReviewWorkspaceRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.aligned_evidence_bundle,
        *request.source_artifacts,
        request.policy.configuration.model_reference,
        *(evidence.reference for evidence in request.policy.configuration.evidence),
        *(item.provenance_artifact for item in request.review_items),
        *(evidence.reference for item in request.review_items for evidence in item.evidence),
        *(
            artifact
            for item in request.review_items
            if item.next_action is not None
            for artifact in item.next_action.required_evidence
        ),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared workflow presentation, provenance, and review evidence.",
        )
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, estimable: bool, review: bool) -> UncertaintyProfile:
    probability = 0.75 if review else 0.95
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if estimable else EstimateState.NOT_ESTIMABLE,
        probability=probability if estimable else None,
        rationale=(
            "Caller-declared review items and references are evaluable within the presentation envelope."
            if estimable
            else "At least one review item is unsupported or unresolved; presentation is safely abstained."
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
            "View ordering, summaries, statuses, and next actions are caller-declared workspace metadata.",
            "The service never infers identity, consent, treatment, kinase activity, or a parent result.",
        ),
    )


def _provenance(
    request: PresentVariantPeptideHumanReviewWorkspaceRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in controls
    )
    input_digests = tuple(
        dict.fromkeys(
            (
                request_digest,
                request.aligned_evidence_bundle.digest,
                request.policy.configuration.model_reference.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(item.provenance_artifact.digest for item in request.review_items),
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1705_MODULE_ID,
        module_version=M1705_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _ordered_items(
    request: PresentVariantPeptideHumanReviewWorkspaceRequest,
) -> tuple[ReviewItem, ...]:
    status_rank = {
        ReviewItemStatus.ABSTAINED: 0,
        ReviewItemStatus.UNRESOLVED: 1,
        ReviewItemStatus.CONFLICTED: 2,
        ReviewItemStatus.LIMITED: 3,
        ReviewItemStatus.SUPPORTED: 4,
    }
    view_rank = {
        ViewKind.DISCREPANCY: 0,
        ViewKind.UNCERTAINTY: 1,
        ViewKind.EVIDENCE_REVIEW: 2,
        ViewKind.PROVENANCE: 3,
        ViewKind.NEXT_ACTION: 4,
        ViewKind.TASK_SUMMARY: 5,
    }
    if request.policy.default_ordering is OrderingPolicy.UNCERTAINTY_FIRST:

        def key(item: ReviewItem) -> tuple[int, int, int]:
            return (view_rank[item.view_kind], status_rank[item.status], item.position)
    else:

        def key(item: ReviewItem) -> tuple[int, int, int]:
            return (status_rank[item.status], view_rank[item.view_kind], item.position)

    return tuple(sorted(request.review_items, key=key))


def _classify(
    request: PresentVariantPeptideHumanReviewWorkspaceRequest,
) -> tuple[WorkspaceStatus, bool, tuple[WorkflowFindingCode, ...]]:
    statuses = {item.status for item in request.review_items}
    findings: list[WorkflowFindingCode] = [WorkflowFindingCode.AUTOMATION_BIAS_GUARD]
    if ReviewItemStatus.ABSTAINED in statuses or ReviewItemStatus.UNRESOLVED in statuses:
        findings.extend(
            (
                WorkflowFindingCode.MISSING_EVIDENCE_SUMMARY,
                WorkflowFindingCode.PROVENANCE_REQUIRED,
            )
        )
        return WorkspaceStatus.ABSTAINED, True, tuple(findings)
    review_required = bool(
        statuses.intersection({ReviewItemStatus.CONFLICTED, ReviewItemStatus.LIMITED})
    )
    if ReviewItemStatus.CONFLICTED in statuses:
        findings.append(WorkflowFindingCode.DISCREPANCY_REQUIRES_REVIEW)
    findings.append(WorkflowFindingCode.PROVISIONAL_ABI_PENDING_REVIEW)
    return WorkspaceStatus.PRESENTED, review_required, tuple(findings)


def _findings(
    codes: tuple[WorkflowFindingCode, ...],
    evidence: tuple[EvidenceReference, ...],
) -> tuple[WorkflowFinding, ...]:
    messages = {
        WorkflowFindingCode.MISSING_EVIDENCE_SUMMARY: "A review item is not safely presentable.",
        WorkflowFindingCode.DISCREPANCY_REQUIRES_REVIEW: "A discrepancy is visible and requires human review.",
        WorkflowFindingCode.AUTOMATION_BIAS_GUARD: "This workspace is a review aid, not an automated decision.",
        WorkflowFindingCode.PROVENANCE_REQUIRED: "Provenance remains required before any claim promotion.",
        WorkflowFindingCode.PROVISIONAL_ABI_PENDING_REVIEW: "The provisional ABI requires governed owner review.",
    }
    return tuple(
        WorkflowFinding(
            finding_id=f"finding.m1705.{code.value}",
            code=code,
            message=messages[code],
            evidence=evidence[:1],
        )
        for code in codes
    )


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_workspace",
            statement="View content, status, ordering, summaries, and next actions are caller-declared.",
        ),
        Limitation(
            code="review_only_output",
            statement="The service emits only a human-review workspace and never emits the variant-peptide parent result.",
        ),
        Limitation(
            code="prohibited_outputs",
            statement="No generic all-omics fusion, kinase activity, treatment recommendation, identity inference, or consent inference is emitted.",
        ),
    ]
    if abstained:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="Unsupported or unresolved review material produces no workspace rather than a negative finding.",
            )
        )
    return tuple(values)


class M1705WorkflowPresentationEngine:
    """Present attributable review items without changing upstream evidence."""

    __slots__ = ()

    def infer(self, request: object) -> VariantPeptideHumanReviewWorkspaceResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: PresentVariantPeptideHumanReviewWorkspaceRequest,
    ) -> VariantPeptideHumanReviewWorkspaceResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        status, review, codes = _classify(request)
        workspace = (
            HumanReviewWorkspace(
                workspace_id=f"workspace.{request_hash.removeprefix('sha256:')}",
                version=request.policy.configuration.version,
                items=tuple(
                    item.model_copy(update={"position": position})
                    for position, item in enumerate(_ordered_items(request))
                ),
                ordering=request.policy.default_ordering,
                automation_bias_warning=(
                    "Reviewers must inspect evidence, uncertainty, discrepancies, and provenance before acting."
                ),
                source_bundle=request.aligned_evidence_bundle,
                evidence=evidence[:64],
            )
            if status is WorkspaceStatus.PRESENTED
            else None
        )
        payload: dict[str, object] = {
            "output_type": "variant_peptide_human_review_workspace",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1705_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "workspace": workspace,
            "findings": _findings(codes, evidence),
            "abstention_reason": (
                None
                if status is WorkspaceStatus.PRESENTED
                else "One or more review items are unsupported or unresolved."
            ),
            "parent_target": "variant_peptide",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if not review else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1705_workspace_presented"
                if status is WorkspaceStatus.PRESENTED
                else "m1705_workspace_abstained",
                rationale=(
                    "All required views are present within the caller-declared support envelope."
                    if status is WorkspaceStatus.PRESENTED and not review
                    else "Review limitations or unresolved material require human review or abstention."
                ),
            ),
            "uncertainty": _uncertainty(
                estimable=status is WorkspaceStatus.PRESENTED,
                review=review,
            ),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(abstained=status is WorkspaceStatus.ABSTAINED),
            "human_review_required": True,
        }
        constructed = VariantPeptideHumanReviewWorkspaceResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideHumanReviewWorkspaceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1705ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1705ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1705ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1705ReplayVerificationError
        return validated


def present_variant_peptide_human_review_workspace(
    request: object,
) -> VariantPeptideHumanReviewWorkspaceResult:
    """Public provisional M17-05 operation."""

    return M1705WorkflowPresentationEngine().infer(request)


__all__ = [
    "M1705AuthorizationError",
    "M1705ReplayVerificationError",
    "M1705WorkflowPresentationEngine",
    "preflight_m1705_authorization",
    "present_variant_peptide_human_review_workspace",
]
