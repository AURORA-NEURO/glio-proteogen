"""Deterministic authorization-first M18-05 workflow presentation engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_05 import (
    M1805_CONTRACT_VERSION,
    M1805_EVIDENCE_CLAIM,
    M1805_MODULE_ID,
    BiomarkerPanelReviewWorkspaceResult,
    HumanReviewWorkspace,
    PresentBiomarkerPanelReviewWorkspaceRequest,
    WorkspaceFinding,
    WorkspaceFindingCode,
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

_REQUEST_ADAPTER: Final = TypeAdapter(PresentBiomarkerPanelReviewWorkspaceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelReviewWorkspaceResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1805AuthorizationError(PermissionError):
    """Caller controls do not authorize workspace presentation."""

    def __init__(self) -> None:
        super().__init__(
            "M18-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1805ReplayVerificationError(ValueError):
    """An M18-05 result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M18-05 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1805_authorization(candidate: object) -> None:
    """Check seven caller-declared controls before traversing workspace sections."""

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
        raise M1805AuthorizationError from None
    if states != expected:
        raise M1805AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1805_authorization(candidate)
    return candidate


def _evidence(
    request: PresentBiomarkerPanelReviewWorkspaceRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
        *(artifact for section in request.sections for artifact in section.source_artifacts),
        *(evidence.reference for section in request.sections for evidence in section.evidence),
        *(evidence.reference for evidence in request.configuration.evidence),
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
        EvidenceReference(reference=artifact, role="evidence", claim=M1805_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, estimable: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if estimable else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if estimable else None,
        rationale=(
            "Caller-declared workspace sections, support and controls are evaluable."
            if estimable
            else "Unsupported input prevents safe workspace presentation."
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
            "Workspace ordering, evidence, uncertainty, discrepancies and next actions are "
            "caller-declared.",
            "The workspace presents limitations and does not infer missing identity or consent.",
        ),
    )


def _provenance(
    request: PresentBiomarkerPanelReviewWorkspaceRequest,
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
                request.upstream_result.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(
                    artifact.digest
                    for section in request.sections
                    for artifact in section.source_artifacts
                ),
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1805_MODULE_ID,
        module_version=M1805_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _classify(
    request: PresentBiomarkerPanelReviewWorkspaceRequest,
) -> tuple[WorkspaceStatus, tuple[WorkspaceFindingCode, ...]]:
    findings: list[WorkspaceFindingCode] = []
    if request.support_decision.status is not SupportStatus.SUPPORTED:
        findings.append(WorkspaceFindingCode.UPSTREAM_UNSUPPORTED)
    if findings:
        return WorkspaceStatus.ABSTAINED, tuple(findings)
    findings.append(WorkspaceFindingCode.PROVISIONAL_ABI_PENDING_REVIEW)
    return WorkspaceStatus.PRESENTED, tuple(findings)


def _findings(
    codes: tuple[WorkspaceFindingCode, ...],
    evidence: tuple[EvidenceReference, ...],
) -> tuple[WorkspaceFinding, ...]:
    messages = {
        WorkspaceFindingCode.REQUIRED_VIEW_MISSING: "A required workspace view is unavailable.",
        WorkspaceFindingCode.UNSAFE_ORDERING: "The workspace default ordering is not safe.",
        WorkspaceFindingCode.AUTOMATION_BIAS_RISK: (
            "The workspace requires an automation-bias warning."
        ),
        WorkspaceFindingCode.UPSTREAM_UNSUPPORTED: (
            "Upstream support is outside the presentation envelope."
        ),
        WorkspaceFindingCode.PROVISIONAL_ABI_PENDING_REVIEW: (
            "The provisional ABI requires governed owner review."
        ),
    }
    return tuple(
        WorkspaceFinding(
            finding_id=f"finding.m1805.{code.value}",
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
            statement=(
                "Sections, evidence, uncertainty, discrepancies, ordering, and next actions are "
                "caller-declared."
            ),
        ),
        Limitation(
            code="human_review_only",
            statement=(
                "The service emits only a human-review workspace and never emits the "
                "biomarker-panel "
                "parent result."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No generic all-omics fusion, kinase activity, treatment recommendation, identity "
                "inference, or consent inference is emitted."
            ),
        ),
    ]
    if abstained:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="Unsupported inputs produce no workspace presentation.",
            )
        )
    return tuple(values)


class M1805WorkflowPresentationEngine:
    """Present complete human-review views with safe default ordering."""

    __slots__ = ()

    def infer(self, request: object) -> BiomarkerPanelReviewWorkspaceResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: PresentBiomarkerPanelReviewWorkspaceRequest,
    ) -> BiomarkerPanelReviewWorkspaceResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        status, codes = _classify(request)
        workspace = None
        if status is WorkspaceStatus.PRESENTED:
            workspace = HumanReviewWorkspace(
                workspace_id=f"workspace.{request_hash.removeprefix('sha256:')}",
                version=M1805_CONTRACT_VERSION,
                sections=request.sections,
                default_section_order=request.default_section_order,
                next_actions=request.next_actions,
                configuration=request.configuration,
                evidence=evidence,
            )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1805_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "workspace": workspace,
            "findings": _findings(codes, evidence),
            "abstention_reason": None
            if workspace is not None
            else "Workspace inputs are not safely supported.",
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": (
                request.support_decision
                if workspace is not None
                else SupportDecision(
                    status=SupportStatus.REVIEW_REQUIRED,
                    reason_code="m1805_workspace_abstained",
                    rationale="Support limitations prevent safe human-review presentation.",
                )
            ),
            "uncertainty": _uncertainty(estimable=workspace is not None),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(abstained=workspace is None),
            "human_review_required": True,
        }
        constructed = BiomarkerPanelReviewWorkspaceResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelReviewWorkspaceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1805ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1805ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1805ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1805ReplayVerificationError
        return validated


def present_biomarker_panel_review_workspace(
    request: object,
) -> BiomarkerPanelReviewWorkspaceResult:
    """Public provisional M18-05 operation."""

    return M1805WorkflowPresentationEngine().infer(request)


__all__ = [
    "M1805AuthorizationError",
    "M1805ReplayVerificationError",
    "M1805WorkflowPresentationEngine",
    "preflight_m1805_authorization",
    "present_biomarker_panel_review_workspace",
]
