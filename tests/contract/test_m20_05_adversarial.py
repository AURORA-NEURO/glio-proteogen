"""Adversarial contract and replay coverage for provisional M20-05."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m20_05 import (
    M2005_M2004_RESULT_MEDIA_TYPE,
    M2005_MODULE_ID,
    HumanReviewWorkspace,
    NextAction,
    OrderingPolicy,
    PresentationConfiguration,
    PresentationPolicy,
    PresentProteinSubtypeHumanReviewWorkspaceRequest,
    ProteinSubtypeHumanReviewWorkspaceResult,
    ReviewItem,
    ReviewItemStatus,
    ViewKind,
    WorkflowFinding,
    WorkflowFindingCode,
    WorkspaceStatus,
    canonical_request_bytes,
    canonical_request_digest,
    canonical_result_payload_bytes,
    result_payload_digest,
    verify_request_digest,
    verify_result_digest,
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


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2005.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2005:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M20-05 review evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2005.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context(request_id: str) -> ExecutionContext:
    artifacts = {
        role: _artifact(role)
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended_use",
            "consent",
        )
    }
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2005.synthetic",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2005.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2005.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2005.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _policy() -> PresentationPolicy:
    configuration_artifact = _artifact("presentation-configuration")
    return PresentationPolicy(
        required_views=tuple(ViewKind),
        default_ordering=OrderingPolicy.SAFE_DEFAULT,
        maximum_items=32,
        configuration=PresentationConfiguration(
            configuration_id="configuration.m2005.synthetic",
            version="1.0.0",
            method="locked_human_review_workspace",
            model_reference=configuration_artifact,
            evidence=(_evidence(configuration_artifact),),
        ),
    )


def _item(
    view: ViewKind,
    position: int,
    *,
    status: ReviewItemStatus = ReviewItemStatus.SUPPORTED,
) -> ReviewItem:
    artifact = _artifact(f"item-{position}")
    escalation = None
    discrepancy_ids: tuple[str, ...] = ()
    if status in {
        ReviewItemStatus.CONFLICTED,
        ReviewItemStatus.UNRESOLVED,
        ReviewItemStatus.ABSTAINED,
    }:
        discrepancy_ids = (f"discrepancy.m2005.{position}",)
        escalation = NextAction(
            action_id=f"action.m2005.{position}",
            label="Review discrepancy",
            rationale="A reviewer must resolve the declared discrepancy.",
        )
    return ReviewItem(
        item_id=f"item.m2005.{position}",
        view_kind=view,
        title=f"{view.value} review",
        position=position,
        status=status,
        evidence_summary="Evidence remains attributable to the caller-declared source.",
        uncertainty_summary="Uncertainty is displayed without conversion to a negative claim.",
        evidence=(_evidence(artifact),),
        discrepancy_ids=discrepancy_ids,
        provenance_artifact=artifact,
        next_action=escalation,
    )


def _request() -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
    aligned = _artifact("aligned", M2005_M2004_RESULT_MEDIA_TYPE)
    policy = _policy()
    items = tuple(_item(view, position) for position, view in enumerate(policy.required_views))
    source_artifacts = (aligned, *(item.provenance_artifact for item in items))
    return PresentProteinSubtypeHumanReviewWorkspaceRequest(
        request_id="request.m2005.synthetic",
        context=_context("request.m2005.synthetic"),
        aligned_evidence_bundle=aligned,
        policy=policy,
        review_items=items,
        source_artifacts=source_artifacts,
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="The presentation service does not estimate this dimension.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def _provenance(request: PresentProteinSubtypeHumanReviewWorkspaceRequest) -> ProvenanceRecord:
    references = request.context.references
    decisions = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id="activity.m2005.synthetic",
        actor_id=request.context.actor_id,
        module_id=M2005_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(request.aligned_evidence_bundle.digest,),
        configuration_digest=sha256_digest(request.policy.configuration.configuration_id),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


def _result() -> ProteinSubtypeHumanReviewWorkspaceResult:
    request = _request()
    support_decision = SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="supported.review_workspace",
        rationale="All required presentation controls are caller-declared and present.",
    )
    uncertainty = _uncertainty()
    provenance = _provenance(request)
    output_evidence = (_evidence(request.aligned_evidence_bundle),)
    limitations = (
        Limitation(
            code="human_review.only",
            statement="The workspace is for human review and emits no parent conclusion.",
        ),
    )
    workspace = HumanReviewWorkspace(
        workspace_id="workspace.m2005.synthetic",
        version="1.0.0",
        items=request.review_items,
        ordering=request.policy.default_ordering,
        automation_bias_warning=(
            "Review the evidence before accepting any machine-suggested ordering."
        ),
        source_bundle=request.aligned_evidence_bundle,
        evidence=(_evidence(request.aligned_evidence_bundle),),
    )
    payload: dict[str, Any] = {
        "output_type": "protein_subtype_human_review_workspace",
        "result_id": "result.m2005.synthetic",
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "request": request.model_dump(mode="json"),
        "status": WorkspaceStatus.PRESENTED.value,
        "workspace": workspace.model_dump(mode="json"),
        "findings": [],
        "abstention_reason": None,
        "parent_target": "protein subtype",
        "emits_parent": False,
        "support_decision": support_decision.model_dump(mode="json"),
        "uncertainty": uncertainty.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
        "evidence": [item.model_dump(mode="json") for item in output_evidence],
        "limitations": [item.model_dump(mode="json") for item in limitations],
        "human_review_required": True,
        "result_digest": "sha256:" + "0" * 64,
    }
    payload["result_digest"] = result_payload_digest(payload)
    payload.update(
        {
            "request": request,
            "status": WorkspaceStatus.PRESENTED,
            "workspace": workspace,
            "findings": (),
            "support_decision": support_decision,
            "uncertainty": uncertainty,
            "provenance": provenance,
            "evidence": output_evidence,
            "limitations": limitations,
        }
    )
    return ProteinSubtypeHumanReviewWorkspaceResult.model_validate(payload, strict=True)


def test_policy_requires_all_safety_critical_views() -> None:
    with pytest.raises(ValueError, match="every safety-critical"):
        PresentationPolicy.model_validate(
            _policy().model_copy(update={"required_views": (ViewKind.TASK_SUMMARY,)}),
            strict=True,
        )


def test_escalated_item_requires_visible_discrepancy_and_next_action() -> None:
    with pytest.raises(ValueError, match="review escalation"):
        ReviewItem.model_validate(
            _item(ViewKind.DISCREPANCY, 0, status=ReviewItemStatus.UNRESOLVED).model_copy(
                update={"discrepancy_ids": (), "next_action": None}
            ),
            strict=True,
        )


def test_request_binds_context_items_and_aligned_source() -> None:
    request = _request()
    assert request.context.request_id == request.request_id
    with pytest.raises(ValueError, match="aligned evidence bundle"):
        PresentProteinSubtypeHumanReviewWorkspaceRequest.model_validate(
            request.model_copy(update={"source_artifacts": request.source_artifacts[1:]}),
            strict=True,
        )


def test_request_rejects_context_limits_views_and_duplicate_sources() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="context must bind"):
        PresentProteinSubtypeHumanReviewWorkspaceRequest.model_validate(
            request.model_copy(update={"context": _context("request.m2005.other")}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="item limit"):
        PresentProteinSubtypeHumanReviewWorkspaceRequest.model_validate(
            request.model_copy(
                update={"policy": request.policy.model_copy(update={"maximum_items": 1})}
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="every policy-required"):
        PresentProteinSubtypeHumanReviewWorkspaceRequest.model_validate(
            request.model_copy(update={"review_items": request.review_items[:-1]}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="unique by id"):
        PresentProteinSubtypeHumanReviewWorkspaceRequest.model_validate(
            request.model_copy(
                update={
                    "source_artifacts": (
                        *request.source_artifacts,
                        request.source_artifacts[0],
                    )
                }
            ),
            strict=True,
        )


def test_workspace_positions_are_contiguous() -> None:
    request = _request()
    with pytest.raises(ValueError, match="contiguous"):
        HumanReviewWorkspace(
            workspace_id="workspace.m2005.bad-position",
            version="1.0.0",
            items=tuple(
                item.model_copy(update={"position": item.position + 1})
                for item in request.review_items
            ),
            ordering=OrderingPolicy.SAFE_DEFAULT,
            automation_bias_warning="Review machine ordering before use.",
            source_bundle=request.aligned_evidence_bundle,
            evidence=(_evidence(request.aligned_evidence_bundle),),
        )


def test_replay_digests_are_stable_and_detect_tampering() -> None:
    request = _request()
    digest = canonical_request_digest(request)
    assert verify_request_digest(request, digest)
    assert canonical_request_bytes(request) == canonical_request_bytes(request)
    result = _result()
    assert verify_result_digest(result, result.result_digest)
    assert canonical_result_payload_bytes(result) == canonical_result_payload_bytes(result)
    assert result.workspace is not None
    altered = result.model_copy(
        update={
            "workspace": result.workspace.model_copy(update={"automation_bias_warning": "tampered"})
        }
    )
    assert not verify_result_digest(altered, result.result_digest)


def test_result_rejects_workspace_or_support_closure_breaks() -> None:
    result = _result()
    with pytest.raises(ValidationError, match="presented result"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(
                update={
                    "workspace": None,
                    "result_digest": result.result_digest,
                }
            ),
            strict=True,
        )


def test_result_rejects_digest_ordering_evidence_source_and_finding_breaks() -> None:
    result = _result()
    assert result.workspace is not None
    with pytest.raises(ValidationError, match="request digest"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(update={"request_digest": sha256_digest("bad-request")}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="output evidence"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(update={"evidence": (), "result_digest": result.result_digest}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="ordering"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(
                update={
                    "workspace": result.workspace.model_copy(
                        update={"ordering": OrderingPolicy.REVIEW_PRIORITY}
                    ),
                    "result_digest": result.result_digest,
                }
            ),
            strict=True,
        )
    reordered = tuple(
        item.model_copy(update={"item_id": f"item.m2005.reordered.{index}"})
        for index, item in enumerate(result.workspace.items)
    )
    with pytest.raises(ValidationError, match="preserve request"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(
                update={
                    "workspace": result.workspace.model_copy(update={"items": reordered}),
                    "result_digest": result.result_digest,
                }
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="source bundle"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(
                update={
                    "workspace": result.workspace.model_copy(
                        update={"source_bundle": _artifact("wrong-source")}
                    ),
                    "result_digest": result.result_digest,
                }
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="abstained result"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(
                update={"status": WorkspaceStatus.ABSTAINED, "result_digest": result.result_digest}
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="result digest"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(update={"result_digest": sha256_digest("bad-result")}),
            strict=True,
        )
    finding = WorkflowFinding(
        finding_id="finding.m2005.duplicate",
        code=WorkflowFindingCode.AUTOMATION_BIAS_GUARD,
        message="Review ordering before use.",
    )
    duplicate_findings = result.model_copy(update={"findings": (finding, finding)})
    with pytest.raises(ValidationError, match="finding ids"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(
                update={
                    "findings": duplicate_findings.findings,
                    "result_digest": result_payload_digest(duplicate_findings),
                }
            ),
            strict=True,
        )
    with pytest.raises(ValidationError, match="presented result"):
        ProteinSubtypeHumanReviewWorkspaceResult.model_validate(
            result.model_copy(
                update={
                    "support_decision": SupportDecision(
                        status=SupportStatus.REVIEW_REQUIRED,
                        reason_code="review.required",
                        rationale="Review is required.",
                    ),
                    "result_digest": result.result_digest,
                }
            ),
            strict=True,
        )
