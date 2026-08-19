"""Deterministic, replay-safe M19-06 discrepancy adjudication."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_06 import (
    M1906_CONTRACT_VERSION,
    M1906_EVIDENCE_CLAIM,
    M1906_MODULE_ID,
    M1906_PROHIBITED_CLAIM_TERMS,
    AdjudicateProteotypeQueueRequest,
    AdjudicationRecord,
    AdjudicationRecordStatus,
    AuditEventType,
    DiscrepancySeverity,
    ImmutableAuditEvent,
    ProteotypeAdjudicationResult,
    QueueEntryState,
    QueueFinding,
    QueueFindingCode,
    QueueResultStatus,
    ReviewDecision,
    ReviewerAssignment,
)
from glio_proteogen.contracts.m19_06.canonical import (
    audit_event_payload_digest,
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

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateProteotypeQueueRequest)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_SYSTEM_ACTOR: Final = "system.m1906"
_CONTROL_STATES: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class M1906AuthorizationError(PermissionError):
    """Raised before queue traversal when caller-declared controls are unsafe."""


class M1906ReplayError(ValueError):
    """Raised when a result no longer binds to its request and payload."""

    def __init__(self, message: str = "M19-06 replay verification failed") -> None:
        super().__init__(message)


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1906_authorization(candidate: object) -> None:
    """Require all seven caller-declared controls before queue traversal."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M1906AuthorizationError("M19-06 requires all seven upstream controls")  # noqa: TRY003
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _state(_member(decision, "state"))
        if actual != expected:
            raise M1906AuthorizationError(  # noqa: TRY003
                f"M19-06 control {name} must be {expected}; received {actual}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M19-06 records reviewer adjudication; it does not estimate biological truth.",
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
            "Adjudication is sensitive to reviewer assignment completeness, blinded decisions, "
            "discrepancy severity and immutable history.",
        ),
    )


def _control_decisions(
    request: AdjudicateProteotypeQueueRequest,
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


def _provenance(request: AdjudicateProteotypeQueueRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1906_MODULE_ID,
        module_version=M1906_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *(item.digest for item in request.source_artifacts),
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: AdjudicateProteotypeQueueRequest) -> tuple[EvidenceReference, ...]:
    items: list[EvidenceReference] = [
        EvidenceReference(reference=item, role="evidence", claim=M1906_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    ]
    items.extend(request.configuration.evidence)
    items.extend(evidence for item in request.entries for evidence in item.evidence)
    items.extend(evidence for item in request.assignments for evidence in item.evidence)
    return tuple(items)


def _claim_texts(request: AdjudicateProteotypeQueueRequest) -> tuple[str, ...]:
    """Collect caller-controlled prose before any review record is emitted."""

    texts: list[str] = [entry.description for entry in request.entries]
    texts.extend(evidence.claim for evidence in request.configuration.evidence)
    texts.extend(
        text
        for assignment in request.assignments
        for text in (assignment.reviewer_role, assignment.rationale)
    )
    texts.extend(evidence.claim for entry in request.entries for evidence in entry.evidence)
    texts.extend(
        evidence.claim for assignment in request.assignments for evidence in assignment.evidence
    )
    return tuple(texts)


def _contains_prohibited_claim(request: AdjudicateProteotypeQueueRequest) -> bool:
    """Reject caller prose that would exceed the M19-06 claims ceiling."""

    return any(
        term.casefold() in text.casefold()
        for text in _claim_texts(request)
        for term in M1906_PROHIBITED_CLAIM_TERMS
    )


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
            statement="The upstream M19-05 artifact and issuer authority are not authenticated.",
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
    request: AdjudicateProteotypeQueueRequest,
    *,
    prohibited_claim_boundary: bool = False,
) -> tuple[QueueFinding, ...]:
    assignments: dict[str, list[ReviewerAssignment]] = {}
    for item in request.assignments:
        assignments.setdefault(item.discrepancy_id, []).append(item)
    findings: list[QueueFinding] = []
    if prohibited_claim_boundary:
        findings.append(
            QueueFinding(
                finding_id=f"finding.{request.request_id}.claim_boundary",
                code=QueueFindingCode.PROHIBITED_CLAIM_BOUNDARY,
                message=(
                    "Caller-controlled adjudication text exceeds the M19-06 claims ceiling; "
                    "no review record is emitted."
                ),
                evidence=request.configuration.evidence or request.entries[0].evidence,
            )
        )
    for entry in request.entries:
        reviews = assignments.get(entry.discrepancy_id, [])
        if entry.state is QueueEntryState.NOT_EVALUABLE:
            findings.append(
                QueueFinding(
                    finding_id=f"finding.{entry.discrepancy_id}.history",
                    code=QueueFindingCode.HISTORY_INCOMPLETE,
                    message="The discrepancy is not evaluable; no adjudication record is emitted.",
                    evidence=entry.evidence,
                )
            )
        if not reviews:
            findings.append(
                QueueFinding(
                    finding_id=f"finding.{entry.discrepancy_id}.assignment",
                    code=QueueFindingCode.ASSIGNMENT_MISSING,
                    message="Every discrepancy requires a blinded reviewer assignment.",
                    evidence=entry.evidence,
                )
            )
            continue
        if entry.state is not QueueEntryState.RESOLVED or any(
            item.decision in {ReviewDecision.DEFER, ReviewDecision.ABSTAIN} for item in reviews
        ):
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
                    evidence=reviews[0].evidence,
                )
            )
    return tuple(findings)


def _audit_event(  # noqa: PLR0913 - explicit audit event fields preserve canonical order.
    *,
    sequence: int,
    event_id: str,
    event_type: AuditEventType,
    actor_token: str,
    action: str,
    record_digest: str,
    previous_event_digest: str | None,
    evidence: tuple[EvidenceReference, ...],
) -> ImmutableAuditEvent:
    payload: dict[str, Any] = {
        "sequence": sequence,
        "event_id": event_id,
        "event_type": event_type,
        "actor_token": actor_token,
        "action": action,
        "record_digest": record_digest,
        "previous_event_digest": previous_event_digest,
        "evidence": evidence,
        "event_digest": _ZERO_DIGEST,
    }
    payload["event_digest"] = audit_event_payload_digest(payload)
    return ImmutableAuditEvent.model_validate(payload, strict=True)


def _history(
    request: AdjudicateProteotypeQueueRequest,
    terminal: AuditEventType,
) -> tuple[ImmutableAuditEvent, ...]:
    events: list[ImmutableAuditEvent] = []
    previous: str | None = None
    record_digest = sha256_digest(
        {"request": canonical_request_digest(request), "terminal": terminal}
    )
    sequence = 1

    def append(event: ImmutableAuditEvent) -> None:
        nonlocal previous
        events.append(event)
        previous = event.event_digest

    append(
        _audit_event(
            sequence=sequence,
            event_id=f"event.{request.request_id}.queue",
            event_type=AuditEventType.QUEUE_CREATED,
            actor_token=_SYSTEM_ACTOR,
            action="queue_created",
            record_digest=record_digest,
            previous_event_digest=previous,
            evidence=request.configuration.evidence or request.entries[0].evidence,
        )
    )
    sequence += 1
    for entry in request.entries:
        append(
            _audit_event(
                sequence=sequence,
                event_id=f"event.{request.request_id}.entry.{entry.discrepancy_id}",
                event_type=AuditEventType.REVIEW_RECORDED,
                actor_token=_SYSTEM_ACTOR,
                action=entry.state.value,
                record_digest=record_digest,
                previous_event_digest=previous,
                evidence=entry.evidence,
            )
        )
        sequence += 1
    for assignment in request.assignments:
        append(
            _audit_event(
                sequence=sequence,
                event_id=f"event.{request.request_id}.assignment.{assignment.assignment_id}",
                event_type=AuditEventType.ASSIGNMENT_CREATED,
                actor_token=assignment.reviewer_token,
                action=assignment.decision.value,
                record_digest=record_digest,
                previous_event_digest=previous,
                evidence=assignment.evidence,
            )
        )
        sequence += 1
    append(
        _audit_event(
            sequence=sequence,
            event_id=f"event.{request.request_id}.terminal",
            event_type=terminal,
            actor_token=_SYSTEM_ACTOR,
            action=terminal.value,
            record_digest=record_digest,
            previous_event_digest=previous,
            evidence=_evidence(request)[:1],
        )
    )
    return tuple(events)


class M1906Engine:
    """Record blinded adjudication with immutable history and safe abstention."""

    def validate_request(self, candidate: object) -> AdjudicateProteotypeQueueRequest:
        preflight_m1906_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def adapt(self, candidate: object) -> ProteotypeAdjudicationResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        claim_boundary_blocked = _contains_prohibited_claim(request)
        findings = _findings(
            request,
            prohibited_claim_boundary=claim_boundary_blocked,
        )
        evidence = _evidence(request)
        blocking = {
            QueueFindingCode.ASSIGNMENT_MISSING,
            QueueFindingCode.HISTORY_INCOMPLETE,
            QueueFindingCode.CRITICAL_UNRESOLVED,
            QueueFindingCode.REVIEW_REQUIRED,
            QueueFindingCode.PROHIBITED_CLAIM_BOUNDARY,
        }
        resolved = not any(item.code in blocking for item in findings)
        record: AdjudicationRecord | None = None
        if resolved:
            record = AdjudicationRecord(
                record_id=f"record.{request.request_id}",
                version=request.configuration.version,
                entries=request.entries,
                assignments=request.assignments,
                history=_history(request, AuditEventType.RESOLVED),
                status=AdjudicationRecordStatus.RESOLVED,
                resolution_summary="All discrepancies have authorized final reviewer decisions.",
                evidence=evidence,
            )
            status = QueueResultStatus.RECORDED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="adjudication_resolved",
                rationale="The immutable review record preserves blinded decisions and evidence.",
            )
            abstention_reason = None
        else:
            status = QueueResultStatus.ABSTAINED
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="adjudication_review_required",
                rationale="Unresolved or unsupported discrepancy evidence cannot be promoted.",
            )
            abstention_reason = (
                "M19-06 abstained because caller-controlled text exceeds the claims ceiling."
                if claim_boundary_blocked
                else "M19-06 abstained because the discrepancy queue is unresolved."
            )
        payload: dict[str, Any] = {
            "output_type": "proteotype_adjudication",
            "result_id": f"result.{request.request_id}",
            "result_version": M1906_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "record": record,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": True,
        }
        payload["result_digest"] = result_payload_digest(
            ProteotypeAdjudicationResult.model_construct(**payload)
        )
        return ProteotypeAdjudicationResult.model_validate(payload, strict=True)

    def replay(self, result: ProteotypeAdjudicationResult) -> ProteotypeAdjudicationResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M1906ReplayError("M19-06 request digest mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M1906ReplayError("M19-06 result payload digest mismatch")  # noqa: TRY003
        try:
            validated = ProteotypeAdjudicationResult.model_validate(
                result.model_dump(mode="python"), strict=True
            )
        except ValueError as exc:
            raise M1906ReplayError from exc
        try:
            expected = self.adapt(validated.request)
        except Exception as exc:
            raise M1906ReplayError("M19-06 deterministic replay failed") from exc  # noqa: TRY003
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            raise M1906ReplayError("M19-06 deterministic replay mismatch")  # noqa: TRY003
        return validated


def adjudicate_proteotype_queue(candidate: object) -> ProteotypeAdjudicationResult:
    return M1906Engine().adapt(candidate)


__all__ = [
    "M1906AuthorizationError",
    "M1906Engine",
    "M1906ReplayError",
    "adjudicate_proteotype_queue",
    "preflight_m1906_authorization",
]
