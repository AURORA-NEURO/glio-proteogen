"""Replay-safe M16-06 reviewer discrepancy adjudication engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_06 import (
    M1606_EVIDENCE_CLAIM,
    M1606_MODULE_ID,
    AdjudicateProteinRnaDiscordanceQueueRequest,
    AdjudicationRecord,
    AdjudicationRecordStatus,
    DiscrepancySeverity,
    ImmutableAuditEvent,
    ProteinRnaDiscordanceAdjudicationResult,
    QueueFinding,
    QueueFindingCode,
    QueueResultStatus,
)
from glio_proteogen.contracts.m16_06.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateProteinRnaDiscordanceQueueRequest)
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


class M1606AuthorizationError(ValueError):
    """Raised before traversal when a required upstream control is unsafe."""


class M1606ReplayError(ValueError):
    """Raised when a replayed result is not bound to the exact request."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m1606_authorization(candidate: object) -> None:
    """Check all seven controls before typed queue or evidence traversal."""

    context = _member(candidate, "context")
    references = _member(context, "references")
    if references is None:
        raise M1606AuthorizationError("M16-06 requires all seven upstream controls")  # noqa: TRY003
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M1606AuthorizationError(  # noqa: TRY003
                f"M16-06 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M16-06 records reviewer adjudication; this boundary does not estimate biology.",
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
            "Review assignment and discrepancy sensitivity are explicit; "
            "unsupported states abstain.",
        ),
    )


def _control_decisions(
    request: AdjudicateProteinRnaDiscordanceQueueRequest,
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


def _provenance(request: AdjudicateProteinRnaDiscordanceQueueRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = (
        request.upstream_result.digest,
        *(artifact.digest for artifact in request.source_artifacts),
        *(evidence.reference.digest for evidence in request.configuration.evidence),
        *(evidence.reference.digest for entry in request.entries for evidence in entry.evidence),
        *(
            evidence.reference.digest
            for assignment in request.assignments
            for evidence in assignment.evidence
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1606_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(
    request: AdjudicateProteinRnaDiscordanceQueueRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1606_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="review_only",
            statement=(
                "This record documents adjudication state and is not a biological "
                "or clinical conclusion."
            ),
        ),
        Limitation(
            code="no_kinase_state",
            statement="KINOPHOS kinase-state ownership remains outside M16-06.",
        ),
        Limitation(
            code="no_identity_inference",
            statement=(
                "Identity, consent, treatment, and upstream evidence are not inferred or mutated."
            ),
        ),
    )


class M1606Engine:
    """Create versioned queue records while retaining every review decision."""

    def validate_request(self, candidate: object) -> AdjudicateProteinRnaDiscordanceQueueRequest:
        preflight_m1606_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def adjudicate(self, candidate: object) -> ProteinRnaDiscordanceAdjudicationResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        assignment_by_entry = {item.discrepancy_id: item for item in request.assignments}
        missing = [
            entry.discrepancy_id
            for entry in request.entries
            if entry.discrepancy_id not in assignment_by_entry
        ]
        unresolved = [
            item for item in request.assignments if item.decision.value in {"defer", "abstain"}
        ]
        critical = any(item.severity is DiscrepancySeverity.CRITICAL for item in request.entries)
        should_abstain = bool(missing) or bool(unresolved) or (critical and not request.assignments)
        if should_abstain:
            result = self._abstained(request, request_digest, missing, unresolved)
        else:
            result = self._recorded(request, request_digest, critical=critical)
        return result

    def replay(
        self,
        result: ProteinRnaDiscordanceAdjudicationResult,
    ) -> ProteinRnaDiscordanceAdjudicationResult:
        expected_request = canonical_request_digest(result.request)
        if result.request_digest != expected_request:
            raise M1606ReplayError("M16-06 result request digest mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M1606ReplayError("M16-06 result payload digest mismatch")  # noqa: TRY003
        expected = self.adjudicate(result.request)
        if expected.model_dump(mode="json") != result.model_dump(mode="json"):
            raise M1606ReplayError("M16-06 deterministic replay result mismatch")  # noqa: TRY003
        return result

    def _recorded(
        self,
        request: AdjudicateProteinRnaDiscordanceQueueRequest,
        request_digest: str,
        *,
        critical: bool,
    ) -> ProteinRnaDiscordanceAdjudicationResult:
        history = tuple(
            ImmutableAuditEvent(
                sequence=index,
                event_id=f"audit.{assignment.assignment_id}",
                event_type="review_decision",
                actor_token=assignment.reviewer_token,
                action=f"{assignment.decision.value}:{assignment.discrepancy_id}",
                record_digest=sha256_digest(assignment),
                evidence=assignment.evidence,
            )
            for index, assignment in enumerate(request.assignments, start=1)
        )
        record = AdjudicationRecord(
            record_id=f"record.{request.request_id}",
            version="0.1.0-provisional",
            entries=request.entries,
            assignments=request.assignments,
            history=history,
            status=AdjudicationRecordStatus.RESOLVED,
            resolution_summary=(
                "Authorized reviewers recorded decisions for every discrepancy; "
                "history is immutable."
            ),
            evidence=tuple(
                EvidenceReference(reference=artifact, role="evidence", claim=M1606_EVIDENCE_CLAIM)
                for artifact in request.source_artifacts
            ),
        )
        findings = (
            (
                QueueFinding(
                    finding_id=f"finding.{request.request_id}.critical-reviewed",
                    code=QueueFindingCode.REVIEW_REQUIRED,
                    message="Critical discrepancy was reviewed; the record remains review-owned.",
                    evidence=record.evidence,
                ),
            )
            if critical
            else ()
        )
        payload: dict[str, Any] = {
            "output_type": "protein_rna_discordance_adjudication",
            "result_id": f"result.{request.request_id}",
            "result_version": "0.1.0-provisional",
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": QueueResultStatus.RECORDED,
            "record": record,
            "findings": findings,
            "abstention_reason": None,
            "parent_target": "protein-RNA discordance",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="review_recorded",
                rationale="All requested discrepancies have immutable reviewer decisions.",
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": True,
        }
        payload["result_digest"] = result_payload_digest(
            ProteinRnaDiscordanceAdjudicationResult.model_construct(**payload)
        )
        return ProteinRnaDiscordanceAdjudicationResult.model_validate(payload, strict=True)

    def _abstained(
        self,
        request: AdjudicateProteinRnaDiscordanceQueueRequest,
        request_digest: str,
        missing: list[str],
        unresolved: list[Any],
    ) -> ProteinRnaDiscordanceAdjudicationResult:
        codes: list[QueueFindingCode] = []
        if missing:
            codes.append(QueueFindingCode.ASSIGNMENT_MISSING)
        if unresolved:
            codes.append(QueueFindingCode.CRITICAL_UNRESOLVED)
        if not codes:
            codes.append(QueueFindingCode.UPSTREAM_UNSUPPORTED)
        findings = tuple(
            QueueFinding(
                finding_id=f"finding.{request.request_id}.{index}",
                code=code,
                message="M16-06 abstains until an authorized reviewer resolves the queue.",
                evidence=_evidence(request),
            )
            for index, code in enumerate(codes, start=1)
        )
        payload: dict[str, Any] = {
            "output_type": "protein_rna_discordance_adjudication",
            "result_id": f"result.{request.request_id}",
            "result_version": "0.1.0-provisional",
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": QueueResultStatus.ABSTAINED,
            "record": None,
            "findings": findings,
            "abstention_reason": (
                "Queue cannot be promoted without complete authorized review history."
            ),
            "parent_target": "protein-RNA discordance",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="review_required",
                rationale="Unresolved or incomplete adjudication is not promoted to a record.",
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": True,
        }
        payload["result_digest"] = result_payload_digest(
            ProteinRnaDiscordanceAdjudicationResult.model_construct(**payload)
        )
        return ProteinRnaDiscordanceAdjudicationResult.model_validate(payload, strict=True)


def adjudicate_protein_rna_discordance_queue(
    candidate: object,
) -> ProteinRnaDiscordanceAdjudicationResult:
    return M1606Engine().adjudicate(candidate)


__all__ = [
    "M1606AuthorizationError",
    "M1606Engine",
    "M1606ReplayError",
    "adjudicate_protein_rna_discordance_queue",
    "preflight_m1606_authorization",
]
