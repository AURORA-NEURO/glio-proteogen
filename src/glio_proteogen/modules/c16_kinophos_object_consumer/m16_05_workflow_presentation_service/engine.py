"""Deterministic, fail-closed M16-05 review workspace runtime."""

from __future__ import annotations

# ruff: noqa: PLR0913, TRY003, TRY301
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_05 import (
    M1605_OPERATION,
    HumanReviewWorkspace,
    PresentProteinRnaReviewWorkspaceRequest,
    ProteinRnaDiscordanceReviewWorkspaceResult,
    WorkspaceConfiguration,
    WorkspaceDiagnostic,
    WorkspaceDiagnosticStatus,
    WorkspaceFindingCode,
    WorkspaceItem,
    WorkspaceItemStatus,
    WorkspacePresentationStatus,
    WorkspaceView,
    WorkspaceViewKind,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m16_05.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.replay import revalidate_replay_result

_REQUEST_ADAPTER = TypeAdapter(PresentProteinRnaReviewWorkspaceRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinRnaDiscordanceReviewWorkspaceResult)
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_PROHIBITED_TOKENS: Final = (
    "kinase",
    "treatment",
    "identity",
    "consent",
    "all-omics",
    "mutation",
    "relabel",
    "erasure",
)
_ABSTENTION_TOKENS: Final = (
    "unsupported",
    "unknown",
    "not_evaluable",
    "not evaluable",
    "ood",
    "out_of_domain",
    "abstain",
    "missing",
)
_DISCREPANCY_TOKENS: Final = (
    "critical",
    "conflict",
    "discrepancy",
    "mismatch",
    "warning",
)


class M1605AuthorizationError(ValueError):
    """Raised when upstream controls do not authorize workspace presentation."""


class M1605InferenceError(ValueError):
    """Raised when a typed workspace request cannot be evaluated safely."""


class M1605ReplayVerificationError(ValueError):
    """Raised when a workspace result digest or replay does not match."""


def _state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1605AuthorizationError("M16-05 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1605AuthorizationError("M16-05 controls are unavailable")
    return state


def preflight_workspace_authorization(request: object) -> None:
    """Check all seven upstream controls without traversing opaque objects."""

    try:
        if isinstance(request, PresentProteinRnaReviewWorkspaceRequest):
            references = request.context.references
            actual = {
                "approved_configuration": references.approved_configuration.state.value,
                "identity_lineage": references.identity_lineage.state.value,
                "provenance": references.provenance.state.value,
                "consent": references.consent.state.value,
                "quality": references.quality.state.value,
                "support": references.support.state.value,
                "intended_use": references.intended_use.state.value,
            }
            if actual != _EXPECTED_STATES:
                raise M1605AuthorizationError("M16-05 controls do not authorize presentation")
            return
        if not isinstance(request, Mapping):
            raise M1605AuthorizationError("M16-05 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1605AuthorizationError("M16-05 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1605AuthorizationError("M16-05 request controls are unavailable")
        for role, expected in _EXPECTED_STATES.items():
            if _state(raw_references.get(role)) != expected:
                raise M1605AuthorizationError("M16-05 controls do not authorize presentation")
    except M1605AuthorizationError:
        raise
    except Exception as error:
        raise M1605AuthorizationError("M16-05 controls are unavailable") from error


def _evidence(request: PresentProteinRnaReviewWorkspaceRequest) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
    ]
    artifacts.extend(
        (
            references.approved_configuration.evidence,
            references.identity_lineage.evidence,
            references.provenance.evidence,
            references.consent.evidence,
            references.quality.evidence,
            references.support.evidence,
            references.intended_use.evidence,
        )
    )
    artifacts.append(
        ArtifactReference(
            artifact_id=request.configuration.configuration_id,
            version=request.configuration.version,
            digest=sha256_digest(request.configuration.model_dump(mode="json")),
            media_type="application/json",
        )
    )
    unique = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M16-05 workflow presentation and review evidence.",
        )
        for artifact in unique.values()
    )


def _declared(request: PresentProteinRnaReviewWorkspaceRequest) -> str:
    values = [
        request.upstream_result.artifact_id,
        request.configuration.configuration_id,
        request.configuration.version,
    ]
    values.extend(item.artifact_id for item in request.source_artifacts)
    return " ".join(values).casefold()


def _item(
    kind: WorkspaceViewKind,
    status: WorkspaceItemStatus,
    evidence: tuple[EvidenceReference, ...],
    source_artifacts: tuple[ArtifactReference, ...],
    *,
    label: str,
    next_action: str,
) -> WorkspaceItem:
    return WorkspaceItem(
        item_id=f"item.{kind.value}",
        title=label,
        summary=(
            "Available for reviewer inspection within the locked workspace."
            if status is WorkspaceItemStatus.AVAILABLE
            else "Reviewer attention is required before this workspace item can be promoted."
        ),
        kind=kind,
        status=status,
        priority=1 if status is WorkspaceItemStatus.AVAILABLE else 2,
        next_action=next_action,
        source_artifacts=source_artifacts,
        evidence=evidence[:1],
    )


def _workspace(
    request: PresentProteinRnaReviewWorkspaceRequest,
    evidence: tuple[EvidenceReference, ...],
    *,
    discrepancy: bool,
) -> HumanReviewWorkspace:
    source_artifacts = (request.upstream_result, *request.source_artifacts)
    item_status = WorkspaceItemStatus.WARNING if discrepancy else WorkspaceItemStatus.AVAILABLE
    views: list[WorkspaceView] = []
    labels = {
        WorkspaceViewKind.TASK: ("Task summary", "Confirm the review question and scope."),
        WorkspaceViewKind.EVIDENCE: (
            "Evidence summary",
            "Inspect source evidence and assay support.",
        ),
        WorkspaceViewKind.UNCERTAINTY: ("Uncertainty", "Inspect the seven uncertainty dimensions."),
        WorkspaceViewKind.DISCREPANCY: (
            "Discrepancies",
            "Resolve or document biological conflicts.",
        ),
        WorkspaceViewKind.PROVENANCE: ("Provenance", "Verify lineage, consent, and configuration."),
        WorkspaceViewKind.NEXT_ACTION: (
            "Next action",
            "Record the reviewer decision or escalation.",
        ),
    }
    for kind in WorkspaceViewKind:
        status = (
            item_status if kind is WorkspaceViewKind.DISCREPANCY else WorkspaceItemStatus.AVAILABLE
        )
        item = _item(
            kind,
            status,
            evidence,
            source_artifacts,
            label=labels[kind][0],
            next_action=labels[kind][1],
        )
        views.append(
            WorkspaceView(
                view_id=f"view.{kind.value}",
                kind=kind,
                title=labels[kind][0],
                purpose=labels[kind][1],
                items=(item,),
                default_item_order=(item.item_id,),
            )
        )
    kinds = tuple(WorkspaceViewKind)
    return HumanReviewWorkspace(
        workspace_id="workspace.protein-rna-review",
        version="1.0.0",
        views=tuple(views),
        configuration=WorkspaceConfiguration(
            configuration_id=request.configuration.configuration_id,
            version=request.configuration.version,
            default_view_order=kinds,
            visible_sections=kinds,
            evidence=evidence[:1],
        ),
        evidence=evidence[:1],
    )


def _diagnostics(
    status: WorkspacePresentationStatus,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[WorkspaceDiagnostic, ...]:
    diagnostic_status = (
        WorkspaceDiagnosticStatus.PASS
        if status is WorkspacePresentationStatus.PRESENTED
        else WorkspaceDiagnosticStatus.WARNING
        if status is WorkspacePresentationStatus.REVIEW_REQUIRED
        else WorkspaceDiagnosticStatus.NOT_EVALUABLE
    )
    return (
        WorkspaceDiagnostic(
            diagnostic_id="diagnostic.workspace.presentation",
            status=diagnostic_status,
            message=(
                "Safe review workspace is presented with required views and ordering."
                if status is WorkspacePresentationStatus.PRESENTED
                else "Workspace requires human review or is not safely evaluable."
            ),
            evidence=evidence[:1],
        ),
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1605_no_kinase_or_treatment",
            statement="The workspace does not infer kinase state or recommend treatment.",
        ),
        Limitation(
            code="m1605_automation_bias_control",
            statement="Safe defaults preserve reviewer ordering and disable automated decisions.",
        ),
        Limitation(
            code="m1605_supported" if supported else "m1605_review_required",
            statement=(
                "All required review views are available within the provisional support domain."
                if supported
                else "Missing, unsupported, or discrepant content requires reviewer action."
            ),
        ),
    )


class M1605PresentationEngine:
    """Stateless deterministic workflow presentation evaluator."""

    def present(self, request: object) -> ProteinRnaDiscordanceReviewWorkspaceResult:
        preflight_workspace_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1605InferenceError from error
        request_digest = sha256_digest(typed.model_dump(mode="json"))
        evidence = _evidence(typed)
        declared = _declared(typed)
        prohibited = any(token in declared for token in _PROHIBITED_TOKENS)
        not_evaluable = any(token in declared for token in _ABSTENTION_TOKENS)
        discrepancy = any(token in declared for token in _DISCREPANCY_TOKENS)
        supported = not prohibited and not not_evaluable and not discrepancy
        review_required = not supported and not prohibited and not not_evaluable
        status = (
            WorkspacePresentationStatus.ABSTAINED
            if prohibited or not_evaluable
            else WorkspacePresentationStatus.PRESENTED
            if supported
            else WorkspacePresentationStatus.REVIEW_REQUIRED
        )
        workspace = (
            None
            if prohibited or not_evaluable
            else _workspace(typed, evidence, discrepancy=discrepancy)
        )
        findings: list[WorkspaceFindingCode] = [
            WorkspaceFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        ]
        if prohibited:
            findings.append(WorkspaceFindingCode.UPSTREAM_UNSUPPORTED)
        elif not_evaluable:
            findings.append(WorkspaceFindingCode.MISSING_TASK_VIEW)
        elif discrepancy:
            findings.append(WorkspaceFindingCode.DISCREPANCY_NOT_VISIBLE)
        if workspace is not None:
            findings.append(WorkspaceFindingCode.PROVENANCE_NOT_VISIBLE)
            findings.append(WorkspaceFindingCode.AUTOMATION_BIAS_CONTROL_MISSING)
        unique_findings = tuple(dict.fromkeys(findings))
        payload: dict[str, Any] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": status,
            "workspace": workspace,
            "diagnostics": _diagnostics(status, evidence),
            "findings": unique_findings,
            "abstention_reason": None
            if supported or review_required
            else "Workspace content is not safely evaluable.",
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED
                if supported
                else SupportStatus.REVIEW_REQUIRED
                if review_required
                else SupportStatus.UNSUPPORTED,
                reason_code="m1605_supported" if supported else "m1605_review_required",
                rationale=(
                    "All required review views are available with safe defaults."
                    if supported
                    else "Workspace presentation is blocked pending support or reviewer action."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteinRnaDiscordanceReviewWorkspaceResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1605InferenceError from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceReviewWorkspaceResult:
        try:
            validated = revalidate_replay_result(_RESULT_ADAPTER, result)
        except Exception as error:
            raise M1605ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1605ReplayVerificationError
        if replay:
            try:
                expected = self.present(validated.request)
            except Exception as error:
                raise M1605ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1605ReplayVerificationError
        return validated


def present_protein_rna_review_workspace(
    request: object,
) -> ProteinRnaDiscordanceReviewWorkspaceResult:
    """Public provisional M16-05 operation."""

    return M1605PresentationEngine().present(request)


__all__ = [
    "M1605_OPERATION",
    "M1605AuthorizationError",
    "M1605InferenceError",
    "M1605PresentationEngine",
    "M1605ReplayVerificationError",
    "preflight_workspace_authorization",
    "present_protein_rna_review_workspace",
]
