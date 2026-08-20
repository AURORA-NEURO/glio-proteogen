"""Deterministic, replay-safe M19-05 human-review workspace presentation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_05 import (
    M1905_CONTRACT_VERSION,
    M1905_EVIDENCE_CLAIM,
    M1905_MAX_EVIDENCE,
    M1905_MODULE_ID,
    M1905_PROHIBITED_CLAIM_TERMS,
    HumanReviewWorkspace,
    PresentProteotypeHumanReviewWorkspaceRequest,
    ProteotypeHumanReviewWorkspaceResult,
    ReviewItemStatus,
    WorkflowFinding,
    WorkflowFindingCode,
    WorkspaceStatus,
)
from glio_proteogen.contracts.m19_05.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
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

_REQUEST_ADAPTER: Final = TypeAdapter(PresentProteotypeHumanReviewWorkspaceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeHumanReviewWorkspaceResult)
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
_FORBIDDEN_CLAIM_TERMS: Final = frozenset(M1905_PROHIBITED_CLAIM_TERMS)


class M1905AuthorizationError(PermissionError):
    """Caller-declared controls do not authorize workspace presentation."""

    def __init__(self) -> None:
        super().__init__(
            "M19-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1905ReplayError(ValueError):
    """A result cannot be reconstructed from its exact request and digest."""

    def __init__(self) -> None:
        super().__init__("M19-05 replay verification failed")


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1905_authorization(candidate: object) -> None:
    """Require every caller-declared control before traversing review material."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            name: _state(_member(_member(references, name), "state")) for name in _CONTROL_STATES
        }
    except Exception:  # noqa: BLE001
        raise M1905AuthorizationError from None
    if states != _CONTROL_STATES:
        raise M1905AuthorizationError


def _evidence(
    request: PresentProteotypeHumanReviewWorkspaceRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts = [request.aligned_evidence_bundle, *request.source_artifacts]
    artifacts.extend(item.provenance_artifact for item in request.review_items)
    artifacts.extend(
        evidence.reference for item in request.review_items for evidence in item.evidence
    )
    artifacts.extend(evidence.reference for evidence in request.policy.configuration.evidence)
    refs = request.context.references
    artifacts.extend(
        (
            refs.approved_configuration.evidence,
            refs.identity_lineage.evidence,
            refs.provenance.evidence,
            refs.consent.evidence,
            refs.quality.evidence,
            refs.support.evidence,
            refs.intended_use.evidence,
        )
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=M1905_EVIDENCE_CLAIM,
        )
        for artifact in tuple(unique.values())[:M1905_MAX_EVIDENCE]
    )


def _claim_texts(
    request: PresentProteotypeHumanReviewWorkspaceRequest,
) -> tuple[str, ...]:
    """Collect caller-controlled presentation text without traversing artifacts."""

    values: list[str] = [
        request.policy.configuration.method,
        *(evidence.claim for evidence in request.policy.configuration.evidence),
    ]
    for item in request.review_items:
        values.extend((item.title, item.evidence_summary, item.uncertainty_summary))
        values.extend(evidence.claim for evidence in item.evidence)
        if item.next_action is not None:
            values.extend((item.next_action.label, item.next_action.rationale))
    return tuple(value.casefold() for value in values)


def _contains_prohibited_claim(request: PresentProteotypeHumanReviewWorkspaceRequest) -> bool:
    texts = _claim_texts(request)
    return any(term in text for term in _FORBIDDEN_CLAIM_TERMS for text in texts)


def _control_decisions(
    request: PresentProteotypeHumanReviewWorkspaceRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    pairs = (
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
            state=str(_state(decision.state)),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=getattr(decision, "binding_digest", None),
        )
        for role, decision in pairs
    )


def _provenance(
    request: PresentProteotypeHumanReviewWorkspaceRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    controls = _control_decisions(request)
    input_digests = tuple(
        dict.fromkeys(
            (
                request_digest,
                request.aligned_evidence_bundle.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(item.provenance_artifact.digest for item in request.review_items),
                *(
                    evidence.reference.digest
                    for item in request.review_items
                    for evidence in item.evidence
                ),
                *(evidence.reference.digest for evidence in request.policy.configuration.evidence),
                *(control.evidence_digest for control in controls),
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1905_MODULE_ID,
        module_version=M1905_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.policy.configuration.model_dump(mode="json")),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def _uncertainty(*, estimable: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if estimable else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if estimable else None,
        rationale=(
            "Caller-declared review evidence and controls are evaluable."
            if estimable
            else "Unsafe or unsupported input prevents a reliable workspace presentation."
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
            "The service presents caller-declared evidence and does not estimate biological truth.",
            "Ordering, uncertainty, discrepancy and next-action fields remain review-visible.",
        ),
    )


def _findings(
    request: PresentProteotypeHumanReviewWorkspaceRequest,
    evidence: tuple[EvidenceReference, ...],
    *,
    abstained: bool,
    claim_boundary_blocked: bool,
) -> tuple[WorkflowFinding, ...]:
    findings: list[WorkflowFinding] = []
    if claim_boundary_blocked:
        findings.append(
            WorkflowFinding(
                finding_id=f"finding.{request.request_id}.claim-boundary",
                code=WorkflowFindingCode.PROHIBITED_CLAIM_BOUNDARY,
                message=("Caller-controlled presentation text exceeds the M19-05 claims ceiling."),
                evidence=evidence[:1],
            )
        )
    if any(
        item.status in {ReviewItemStatus.CONFLICTED, ReviewItemStatus.UNRESOLVED}
        for item in request.review_items
    ):
        findings.append(
            WorkflowFinding(
                finding_id=f"finding.{request.request_id}.discrepancy-review",
                code=WorkflowFindingCode.DISCREPANCY_REQUIRES_REVIEW,
                message="Conflicted or unresolved review items require human review.",
                evidence=evidence[:1],
            )
        )
    findings.append(
        WorkflowFinding(
            finding_id=f"finding.{request.request_id}.automation-bias",
            code=WorkflowFindingCode.AUTOMATION_BIAS_GUARD,
            message="Review evidence and uncertainty before accepting any next action.",
            evidence=evidence[:1],
        )
    )
    findings.append(
        WorkflowFinding(
            finding_id=f"finding.{request.request_id}.provenance",
            code=WorkflowFindingCode.PROVENANCE_REQUIRED,
            message="All presented material remains linked to caller-declared provenance.",
            evidence=evidence[:1],
        )
    )
    if abstained:
        findings.append(
            WorkflowFinding(
                finding_id=f"finding.{request.request_id}.abstention",
                code=WorkflowFindingCode.MISSING_EVIDENCE_SUMMARY,
                message="Workspace presentation abstained because support is unsafe.",
                evidence=evidence[:1],
            )
        )
    else:
        findings.append(
            WorkflowFinding(
                finding_id=f"finding.{request.request_id}.provisional-abi",
                code=WorkflowFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="The provisional ABI requires governed owner review.",
                evidence=evidence[:1],
            )
        )
    return tuple(findings)


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_workspace",
            statement=(
                "Views, evidence summaries, uncertainty, discrepancies, provenance and next "
                "actions are caller-declared."
            ),
        ),
        Limitation(
            code="human_review_only",
            statement=(
                "The service emits a review workspace and never emits a proteotype parent result."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, generic all-omics fusion, direct treatment recommendation, "
                "identity inference or consent inference is emitted."
            ),
        ),
    ]
    if abstained:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="Unsafe support produces no workspace presentation.",
            )
        )
    return tuple(values)


class M1905Engine:
    """Present a complete, attributable human-review workspace deterministically."""

    __slots__ = ()

    def validate_request(
        self,
        candidate: object,
    ) -> PresentProteotypeHumanReviewWorkspaceRequest:
        preflight_m1905_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def present(self, candidate: object) -> ProteotypeHumanReviewWorkspaceResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        claim_boundary_blocked = _contains_prohibited_claim(request)
        abstained = claim_boundary_blocked or any(
            item.status is ReviewItemStatus.ABSTAINED for item in request.review_items
        )
        workspace = None
        if not abstained:
            workspace = HumanReviewWorkspace(
                workspace_id=f"workspace.{request_digest.removeprefix('sha256:')}",
                version=request.policy.configuration.version,
                items=request.review_items,
                ordering=request.policy.default_ordering,
                safe_default_order=True,
                automation_bias_warning=(
                    "Review evidence and uncertainty before accepting any suggested next action."
                ),
                source_bundle=request.aligned_evidence_bundle,
                evidence=evidence,
            )
        support = (
            SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m1905_workspace_abstained",
                rationale="An abstained review item prevents safe workspace presentation.",
            )
            if workspace is None
            else SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1905_workspace_presented",
                rationale="All declared workspace items satisfy the presentation envelope.",
            )
        )
        payload: dict[str, Any] = {
            "output_type": "proteotype_human_review_workspace",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M1905_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": WorkspaceStatus.ABSTAINED if workspace is None else WorkspaceStatus.PRESENTED,
            "workspace": workspace,
            "findings": _findings(
                request,
                evidence,
                abstained=workspace is None,
                claim_boundary_blocked=claim_boundary_blocked,
            ),
            "abstention_reason": (
                "A prohibited caller claim exceeds the M19-05 claims ceiling."
                if claim_boundary_blocked
                else (
                    "An abstained review item prevents safe workspace presentation."
                    if workspace is None
                    else None
                )
            ),
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(estimable=workspace is not None),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": _limitations(abstained=workspace is None),
            "human_review_required": True,
        }
        payload["result_digest"] = result_payload_digest(
            ProteotypeHumanReviewWorkspaceResult.model_construct(**payload)
        )
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        candidate: object,
        *,
        replay: bool = True,
    ) -> ProteotypeHumanReviewWorkspaceResult:
        try:
            result = _RESULT_ADAPTER.validate_python(candidate, strict=True)
            if result.request_digest != canonical_request_digest(result.request):
                raise M1905ReplayError  # noqa: TRY301
            if result.result_digest != result_payload_digest(result):
                raise M1905ReplayError  # noqa: TRY301
            if replay and self.present(result.request) != result:
                raise M1905ReplayError  # noqa: TRY301
        except M1905ReplayError:
            raise
        except Exception as error:
            raise M1905ReplayError from error
        return result


def present_proteotype_human_review_workspace(
    candidate: object,
) -> ProteotypeHumanReviewWorkspaceResult:
    """Public M19-05 operation."""

    return M1905Engine().present(candidate)


__all__ = [
    "M1905AuthorizationError",
    "M1905Engine",
    "M1905ReplayError",
    "preflight_m1905_authorization",
    "present_proteotype_human_review_workspace",
]
