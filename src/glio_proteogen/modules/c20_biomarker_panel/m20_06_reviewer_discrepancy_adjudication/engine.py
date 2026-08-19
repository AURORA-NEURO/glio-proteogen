"""Deterministic, replay-safe M20-06 discrepancy adjudication."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_06 import (
    M2006_CONTRACT_VERSION,
    M2006_EVIDENCE_CLAIM,
    M2006_MAX_EVIDENCE,
    M2006_MODULE_ID,
    AdjudicateProteinSubtypeQueueRequest,
    AdjudicationRecord,
    AdjudicationRecordStatus,
    DiscrepancySeverity,
    ImmutableAuditEvent,
    ProteinSubtypeAdjudicationResult,
    QueueEntryState,
    QueueFinding,
    QueueFindingCode,
    QueueResultStatus,
    ReviewDecision,
    ReviewerAssignment,
)
from glio_proteogen.contracts.m20_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateProteinSubtypeQueueRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeAdjudicationResult)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_SYSTEM_ACTOR: Final = "system.m2006"
_CONTROL_STATES: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class M2006AuthorizationError(PermissionError):
    """Raised before queue traversal when caller-declared controls are unsafe."""


class M2006ReplayError(ValueError):
    """Raised when a result no longer binds to its request or payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m2006_authorization(candidate: object) -> None:
    """Require all seven caller-declared controls before queue traversal."""

    try:
        references = _member(_member(candidate, "context"), "references")
    except Exception as error:
        raise M2006AuthorizationError from error
    if references is None:
        raise M2006AuthorizationError("M20-06 requires all seven upstream controls")  # noqa: TRY003
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M2006AuthorizationError(  # noqa: TRY003
                f"M20-06 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M20-06 records review decisions and does not estimate biological truth.",
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
    request: AdjudicateProteinSubtypeQueueRequest,
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


def _provenance(request: AdjudicateProteinSubtypeQueueRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M2006_MODULE_ID,
        module_version=M2006_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=sha256_digest(request.configuration.model_dump(mode="json")),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: AdjudicateProteinSubtypeQueueRequest) -> tuple[EvidenceReference, ...]:
    items: list[EvidenceReference] = [
        EvidenceReference(reference=artifact, role="evidence", claim=M2006_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    ]
    items.extend(request.configuration.evidence)
    items.extend(evidence for entry in request.entries for evidence in entry.evidence)
    items.extend(evidence for assignment in request.assignments for evidence in assignment.evidence)
    selected: list[EvidenceReference] = []
    seen: set[str] = set()
    for evidence in items:
        if evidence.reference.digest not in seen and len(selected) < M2006_MAX_EVIDENCE:
            selected.append(evidence)
            seen.add(evidence.reference.digest)
    return tuple(selected)


def _findings(request: AdjudicateProteinSubtypeQueueRequest) -> tuple[QueueFinding, ...]:
    assignments: dict[str, list[ReviewerAssignment]] = {}
    for assignment in request.assignments:
        assignments.setdefault(assignment.discrepancy_id, []).append(assignment)
    findings: list[QueueFinding] = []
    for entry in request.entries:
        reviews = assignments.get(entry.discrepancy_id, [])
        if entry.state is QueueEntryState.NOT_EVALUABLE:
            findings.append(
                QueueFinding(
                    finding_id=f"finding.{entry.discrepancy_id}.not-evaluable",
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
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _history(
    request: AdjudicateProteinSubtypeQueueRequest,
    terminal: str,
) -> tuple[ImmutableAuditEvent, ...]:
    record_digest = sha256_digest(
        {"request": canonical_request_digest(request), "terminal": terminal}
    )
    evidence = _evidence(request)
    events: list[ImmutableAuditEvent] = []
    sequence = 1

    def append(
        event_type: str,
        actor_token: str,
        action: str,
        refs: tuple[EvidenceReference, ...],
    ) -> None:
        nonlocal sequence
        events.append(
            ImmutableAuditEvent(
                sequence=sequence,
                event_id=f"event.{request.request_id}.{sequence}",
                event_type=event_type,
                actor_token=actor_token,
                action=action,
                record_digest=record_digest,
                evidence=refs,
            )
        )
        sequence += 1

    append("queue_created", _SYSTEM_ACTOR, "queue_created", evidence[:1])
    for entry in request.entries:
        append("entry_recorded", _SYSTEM_ACTOR, entry.state.value, entry.evidence)
    for assignment in request.assignments:
        append(
            "assignment_recorded",
            assignment.reviewer_token,
            assignment.decision.value,
            assignment.evidence,
        )
    append("terminal", _SYSTEM_ACTOR, terminal, evidence[:1])
    return tuple(events)


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
            statement="The upstream M20-05 artifact and issuer authority are not authenticated.",
        ),
        Limitation(
            code="no_kinase_treatment_or_all_omics",
            statement=(
                "Kinase, all-omics, treatment, identity and subtype claims remain outside "
                "this queue."
            ),
        ),
    )


class M2006Engine:
    """Record blinded adjudication with immutable history and safe abstention."""

    def validate_request(self, candidate: object) -> AdjudicateProteinSubtypeQueueRequest:
        preflight_m2006_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def adjudicate(self, candidate: object) -> ProteinSubtypeAdjudicationResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        findings = _findings(request)
        evidence = _evidence(request)
        blocking = {
            QueueFindingCode.ASSIGNMENT_MISSING,
            QueueFindingCode.HISTORY_INCOMPLETE,
            QueueFindingCode.CRITICAL_UNRESOLVED,
            QueueFindingCode.REVIEW_REQUIRED,
        }
        resolved = not any(item.code in blocking for item in findings)
        record: AdjudicationRecord | None = None
        if resolved:
            record = AdjudicationRecord(
                record_id=f"record.{request.request_id}",
                version=request.configuration.version,
                entries=request.entries,
                assignments=request.assignments,
                history=_history(request, "resolved"),
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
            abstention_reason = "M20-06 abstained because the discrepancy queue is unresolved."
        payload: dict[str, Any] = {
            "output_type": "protein_subtype_adjudication",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M2006_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "record": record,
            "findings": findings,
            "abstention_reason": abstention_reason,
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
            ProteinSubtypeAdjudicationResult.model_construct(**payload)
        )
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(self, result: ProteinSubtypeAdjudicationResult) -> ProteinSubtypeAdjudicationResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2006ReplayError("M20-06 result request digest mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2006ReplayError("M20-06 result payload digest mismatch")  # noqa: TRY003
        try:
            validated = ProteinSubtypeAdjudicationResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.adjudicate(validated.request)
        except M2006ReplayError:
            raise
        except Exception as error:
            raise M2006ReplayError("M20-06 replay result validation failed") from error  # noqa: TRY003
        if canonical_json_bytes(expected) != canonical_json_bytes(validated):
            raise M2006ReplayError("M20-06 deterministic replay mismatch")  # noqa: TRY003
        return validated


def adjudicate_protein_subtype_discrepancy_queue(
    candidate: object,
) -> ProteinSubtypeAdjudicationResult:
    return M2006Engine().adjudicate(candidate)


__all__ = [
    "M2006AuthorizationError",
    "M2006Engine",
    "M2006ReplayError",
    "adjudicate_protein_subtype_discrepancy_queue",
    "preflight_m2006_authorization",
]
