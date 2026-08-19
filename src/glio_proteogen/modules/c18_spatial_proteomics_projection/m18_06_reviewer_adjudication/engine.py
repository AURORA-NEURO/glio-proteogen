"""Replay-safe reviewer discrepancy adjudication for M18-06."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_06 import (
    M1806_EVIDENCE_CLAIM,
    M1806_MODULE_ID,
    AdjudicateBiomarkerPanelQueueRequest,
    AdjudicationRecord,
    AdjudicationRecordStatus,
    BiomarkerPanelAdjudicationResult,
    DiscrepancySeverity,
    ImmutableAuditEvent,
    QueueEntryState,
    QueueFinding,
    QueueFindingCode,
    QueueResultStatus,
    ReviewDecision,
)
from glio_proteogen.contracts.m18_06.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateBiomarkerPanelQueueRequest)
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


class M1806AuthorizationError(ValueError):
    """Raised before queue traversal when controls are unsafe."""


class M1806ReplayError(ValueError):
    """Raised when a result digest no longer binds to its request or payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m1806_authorization(candidate: object) -> None:
    """Require all seven caller-declared controls before adjudication traversal."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M1806AuthorizationError("M18-06 requires all seven upstream controls")  # noqa: TRY003
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M1806AuthorizationError(  # noqa: TRY003
                f"M18-06 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M18-06 records reviewer adjudication; it does not estimate biological truth.",
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
            "Adjudication state is sensitive to reviewer assignment completeness, blinded "
            "decisions, discrepancy severity and immutable history.",
        ),
    )


def _control_decisions(
    request: AdjudicateBiomarkerPanelQueueRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    records: list[ControlDecisionRecord] = []
    for role, decision in (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    ):
        records.append(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
            )
        )
    records.extend(
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
    return tuple(records)


def _provenance(request: AdjudicateBiomarkerPanelQueueRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1806_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: AdjudicateBiomarkerPanelQueueRequest) -> tuple[EvidenceReference, ...]:
    items: list[EvidenceReference] = [
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=M1806_EVIDENCE_CLAIM,
        )
        for artifact in request.source_artifacts
    ]
    items.extend(request.configuration.evidence)
    for entry in request.entries:
        items.extend(entry.evidence)
    for assignment in request.assignments:
        items.extend(assignment.evidence)
    return tuple(items)


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="review_record_only",
            statement=(
                "This module records caller-declared adjudication and does not infer biology."
            ),
        ),
        Limitation(
            code="upstream_not_authenticated",
            statement=(
                "The upstream M18-05 workflow artifact and issuer authority are not authenticated."
            ),
        ),
        Limitation(
            code="no_kinase_treatment_or_all_omics",
            statement=(
                "Kinase, all-omics, treatment, identity and subtype claims remain outside "
                "this queue."
            ),
        ),
    )


def _findings(
    request: AdjudicateBiomarkerPanelQueueRequest,
) -> tuple[QueueFinding, ...]:
    assignments_by_entry = {item.discrepancy_id: item for item in request.assignments}
    findings: list[QueueFinding] = []
    for entry in request.entries:
        assignment = assignments_by_entry.get(entry.discrepancy_id)
        if entry.state is QueueEntryState.NOT_EVALUABLE:
            findings.append(
                QueueFinding(
                    finding_id=f"finding.{entry.discrepancy_id}.history",
                    code=QueueFindingCode.HISTORY_INCOMPLETE,
                    message="The discrepancy is not evaluable; no adjudication record is emitted.",
                    evidence=entry.evidence,
                )
            )
        if assignment is None:
            findings.append(
                QueueFinding(
                    finding_id=f"finding.{entry.discrepancy_id}.assignment",
                    code=QueueFindingCode.ASSIGNMENT_MISSING,
                    message="Every discrepancy requires a blinded reviewer assignment.",
                    evidence=entry.evidence,
                )
            )
            continue
        if entry.state is not QueueEntryState.RESOLVED or assignment.decision in {
            ReviewDecision.DEFER,
            ReviewDecision.ABSTAIN,
        }:
            code = (
                QueueFindingCode.CRITICAL_UNRESOLVED
                if entry.severity is DiscrepancySeverity.CRITICAL
                else QueueFindingCode.REVIEW_REQUIRED
            )
            findings.append(
                QueueFinding(
                    finding_id=f"finding.{entry.discrepancy_id}.review",
                    code=code,
                    message="The discrepancy remains unresolved or is deferred for escalation.",
                    evidence=assignment.evidence,
                )
            )
    return tuple(findings)


def _history(request: AdjudicateBiomarkerPanelQueueRequest) -> tuple[ImmutableAuditEvent, ...]:
    events: list[ImmutableAuditEvent] = []
    sequence = 1
    for entry in request.entries:
        events.append(
            ImmutableAuditEvent(
                sequence=sequence,
                event_id=f"event.{request.request_id}.entry.{entry.discrepancy_id}",
                event_type="queue_entry_recorded",
                actor_token="system.m1806",  # noqa: S106
                action=entry.state.value,
                record_digest=sha256_digest(entry),
                evidence=entry.evidence,
            )
        )
        sequence += 1
    for assignment in request.assignments:
        events.append(
            ImmutableAuditEvent(
                sequence=sequence,
                event_id=f"event.{request.request_id}.assignment.{assignment.assignment_id}",
                event_type="review_assignment_recorded",
                actor_token=assignment.reviewer_token,
                action=assignment.decision.value,
                record_digest=sha256_digest(assignment),
                evidence=assignment.evidence,
            )
        )
        sequence += 1
    return tuple(events)


class M1806Engine:
    """Record blinded adjudication with immutable history and escalation."""

    def validate_request(self, candidate: object) -> AdjudicateBiomarkerPanelQueueRequest:
        preflight_m1806_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def adapt(self, candidate: object) -> BiomarkerPanelAdjudicationResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        findings = _findings(request)
        evidence = _evidence(request)
        blockers = {QueueFindingCode.ASSIGNMENT_MISSING, QueueFindingCode.HISTORY_INCOMPLETE}
        if any(item.code in blockers for item in findings):
            status = QueueResultStatus.ABSTAINED
            record = None
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="adjudication_record_incomplete",
                rationale=(
                    "No record is emitted until every discrepancy has blinded assignment "
                    "and evaluable history."
                ),
            )
            abstention_reason = "Adjudication queue abstained on missing assignment or history."
        else:
            history = _history(request)
            resolved = all(
                entry.state is QueueEntryState.RESOLVED
                and next(
                    item.decision
                    for item in request.assignments
                    if item.discrepancy_id == entry.discrepancy_id
                )
                in {ReviewDecision.ACCEPT, ReviewDecision.REJECT}
                for entry in request.entries
            )
            record = AdjudicationRecord(
                record_id=f"record.{request.request_id}",
                version=request.configuration.version,
                entries=request.entries,
                assignments=request.assignments,
                history=history,
                status=(
                    AdjudicationRecordStatus.RESOLVED
                    if resolved
                    else AdjudicationRecordStatus.ESCALATED
                ),
                resolution_summary=(
                    "All discrepancy entries have authorized reviewer decisions."
                    if resolved
                    else None
                ),
                evidence=evidence,
            )
            status = QueueResultStatus.RECORDED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code=("adjudication_resolved" if resolved else "adjudication_escalated"),
                rationale=(
                    "The immutable review record preserves blinded decisions and escalation state."
                ),
            )
            abstention_reason = None
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_adjudication",
            "result_id": f"result.{request.request_id}",
            "result_version": "0.1.0-provisional",
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "record": record,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": True,
        }
        payload["result_digest"] = result_payload_digest(
            BiomarkerPanelAdjudicationResult.model_construct(**payload)
        )
        return BiomarkerPanelAdjudicationResult.model_validate(payload, strict=True)

    def replay(
        self,
        result: BiomarkerPanelAdjudicationResult,
    ) -> BiomarkerPanelAdjudicationResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M1806ReplayError("M18-06 result request digest mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M1806ReplayError("M18-06 result payload digest mismatch")  # noqa: TRY003
        expected = self.adapt(result.request)
        if expected.model_dump(mode="json") != result.model_dump(mode="json"):
            raise M1806ReplayError("M18-06 deterministic replay mismatch")  # noqa: TRY003
        return result


def adjudicate_biomarker_panel_queue(
    candidate: object,
) -> BiomarkerPanelAdjudicationResult:
    return M1806Engine().adapt(candidate)


__all__ = [
    "M1806AuthorizationError",
    "M1806Engine",
    "M1806ReplayError",
    "adjudicate_biomarker_panel_queue",
    "preflight_m1806_authorization",
]
