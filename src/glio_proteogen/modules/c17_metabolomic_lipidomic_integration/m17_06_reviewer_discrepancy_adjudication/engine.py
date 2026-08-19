"""Deterministic, fail-closed M17-06 adjudication runtime."""

from __future__ import annotations

# ruff: noqa: TRY003, TRY301
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_06 import (
    M1706_MODULE_ID,
    AdjudicateVariantPeptideDiscrepancyQueueRequest,
    AdjudicationRecord,
    AdjudicationRecordStatus,
    ImmutableAuditEvent,
    QueueEntryState,
    QueueFinding,
    QueueFindingCode,
    QueueResultStatus,
    VariantPeptideAdjudicationResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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

_REQUEST_ADAPTER = TypeAdapter(AdjudicateVariantPeptideDiscrepancyQueueRequest)
_RESULT_ADAPTER = TypeAdapter(VariantPeptideAdjudicationResult)
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_ABSTENTION_TOKENS: Final = (
    "unsupported",
    "unknown",
    "missing",
    "not_evaluable",
    "not evaluable",
    "ood",
    "out_of_domain",
    "abstain",
)
_PROHIBITED_TOKENS: Final = (
    "kinase",
    "treatment",
    "identity_inference",
    "identity inference",
    "consent_inference",
    "consent inference",
    "all-omics",
    "all_omics",
    "relabel",
    "erase disagreement",
    "negative finding",
)


class M1706AuthorizationError(ValueError):
    """Raised when upstream controls do not authorize adjudication."""


class M1706ExportError(ValueError):
    """Raised when a typed M17-06 request cannot be evaluated safely."""


class M1706ReplayVerificationError(ValueError):
    """Raised when an adjudication result digest or replay does not match."""


def _state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1706AuthorizationError("M17-06 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1706AuthorizationError("M17-06 controls are unavailable")
    return state


def preflight_adjudication_authorization(request: object) -> None:
    """Check all seven caller-declared controls before queue adjudication."""

    try:
        if isinstance(request, AdjudicateVariantPeptideDiscrepancyQueueRequest):
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
                raise M1706AuthorizationError("M17-06 controls do not authorize adjudication")
            return
        if not isinstance(request, Mapping):
            raise M1706AuthorizationError("M17-06 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1706AuthorizationError("M17-06 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1706AuthorizationError("M17-06 request controls are unavailable")
        for role, expected in _EXPECTED_STATES.items():
            if _state(raw_references.get(role)) != expected:
                raise M1706AuthorizationError("M17-06 controls do not authorize adjudication")
    except M1706AuthorizationError:
        raise
    except Exception as error:
        raise M1706AuthorizationError("M17-06 controls are unavailable") from error


def _evidence(
    request: AdjudicateVariantPeptideDiscrepancyQueueRequest,
) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
        request.configuration.evidence[0].reference
        if request.configuration.evidence
        else request.source_artifacts[0],
    ]
    for entry in request.entries:
        artifacts.extend(item.reference for item in entry.evidence)
    for assignment in request.assignments:
        artifacts.extend(item.reference for item in assignment.evidence)
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
    unique = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M17-06 discrepancy and adjudication evidence.",
        )
        for artifact in unique.values()
    )


def _declared(request: AdjudicateVariantPeptideDiscrepancyQueueRequest) -> str:
    values = [
        request.request_id,
        request.configuration.configuration_id,
        *(item.discrepancy_id for item in request.entries),
        *(item.description for item in request.entries),
        *(item.reason_code.value for item in request.entries),
        *(item.reference.artifact_id for entry in request.entries for item in entry.evidence),
        *(assignment.reviewer_role for assignment in request.assignments),
        *(assignment.reviewer_token for assignment in request.assignments),
        *(assignment.rationale for assignment in request.assignments),
        *(item.artifact_id for item in request.source_artifacts),
    ]
    return " ".join(values).casefold()


def _uncertainty(*, supported: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "All queue entries have blinded final decisions and immutable history can be emitted."
            if supported
            else "Unsupported, unresolved, or boundary-marked review material was not promotable."
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
            "Reviewer disagreement remains explicit; this module never mutates upstream evidence.",
        ),
    )


def _provenance(
    request: AdjudicateVariantPeptideDiscrepancyQueueRequest,
    request_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = (
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
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1706_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(request_digest, request.upstream_result.digest),
        configuration_digest=request.configuration.evidence[0].reference.digest
        if request.configuration.evidence
        else request.source_artifacts[0].digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1706_no_kinase_or_treatment",
            statement="Adjudication does not infer kinase state or recommend treatment.",
        ),
        Limitation(
            code="m1706_immutable_history",
            statement="Every promoted record carries ordered immutable audit history.",
        ),
        Limitation(
            code="m1706_supported" if supported else "m1706_review_required",
            statement=(
                "All entries have final blinded decisions under the locked workspace policy."
                if supported
                else (
                    "Unsupported, missing, conflicting, or unresolved material requires abstention."
                )
            ),
        ),
    )


class M1706AdjudicationEngine:
    """Stateless deterministic reviewer queue evaluator."""

    def export(self, request: object) -> VariantPeptideAdjudicationResult:
        preflight_adjudication_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1706ExportError from error
        request_digest = canonical_request_digest(typed)
        evidence = _evidence(typed)
        declared = _declared(typed)
        boundary = any(token in declared for token in _ABSTENTION_TOKENS + _PROHIBITED_TOKENS)
        final_decisions = all(
            item.decision.value in {"accept", "reject"} for item in typed.assignments
        )
        all_resolved = all(item.state is QueueEntryState.RESOLVED for item in typed.entries)
        promotable = not boundary and final_decisions and all_resolved
        findings: list[QueueFinding] = [
            QueueFinding(
                finding_id="finding.provisional-abi",
                code=QueueFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="The M17-06 adjudication ABI remains provisional.",
                evidence=evidence[:1],
            )
        ]
        if boundary:
            findings.append(
                QueueFinding(
                    finding_id="finding.upstream-unsupported",
                    code=QueueFindingCode.UPSTREAM_UNSUPPORTED,
                    message="Boundary or unsupported review material cannot be promoted.",
                    evidence=evidence[:1],
                )
            )
        elif not final_decisions:
            findings.append(
                QueueFinding(
                    finding_id="finding.review-required",
                    code=QueueFindingCode.REVIEW_REQUIRED,
                    message="Every discrepancy requires a final blinded review decision.",
                    evidence=evidence[:1],
                )
            )
        elif not all_resolved:
            findings.append(
                QueueFinding(
                    finding_id="finding.critical-unresolved",
                    code=QueueFindingCode.CRITICAL_UNRESOLVED,
                    message="Queue entries remain unresolved or escalated.",
                    evidence=evidence[:1],
                )
            )
        record: AdjudicationRecord | None = None
        if promotable:
            record = AdjudicationRecord(
                record_id=f"record.{request_digest.removeprefix('sha256:')}",
                version="1.0.0",
                entries=typed.entries,
                assignments=typed.assignments,
                history=(
                    ImmutableAuditEvent(
                        sequence=1,
                        event_id=f"event.{request_digest.removeprefix('sha256:')}",
                        event_type="queue_resolution",
                        actor_token="reviewer.opaque.runtime",  # noqa: S106
                        action="resolved adjudication queue",
                        record_digest=sha256_digest({"request_digest": request_digest}),
                        evidence=evidence[:1],
                    ),
                ),
                status=AdjudicationRecordStatus.RESOLVED,
                resolution_summary="All queued discrepancies received final blinded decisions.",
                evidence=evidence,
            )
        support_status = (
            SupportStatus.SUPPORTED
            if promotable
            else (SupportStatus.UNSUPPORTED if boundary else SupportStatus.REVIEW_REQUIRED)
        )
        payload: dict[str, Any] = {
            "output_type": "variant_peptide_adjudication",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": "0.1.0-provisional",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": (
                QueueResultStatus.RECORDED if record is not None else QueueResultStatus.ABSTAINED
            ),
            "record": record,
            "findings": tuple(findings),
            "abstention_reason": None
            if record is not None
            else (
                "Review material is unsupported or prohibited for this module."
                if boundary
                else "Queue is not safely promotable until every discrepancy is resolved."
            ),
            "support_decision": SupportDecision(
                status=support_status,
                reason_code="m1706_recorded" if record is not None else "m1706_review_required",
                rationale=(
                    "A complete immutable adjudication record was constructed."
                    if record is not None
                    else (
                        "Safe abstention preserves disagreement and prevents unsupported promotion."
                    )
                ),
            ),
            "uncertainty": _uncertainty(supported=record is not None),
            "provenance": _provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=record is not None),
            "human_review_required": True,
        }
        constructed = VariantPeptideAdjudicationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1706ExportError from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideAdjudicationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1706ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1706ReplayVerificationError
        if replay:
            try:
                expected = self.export(validated.request)
            except Exception as error:
                raise M1706ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1706ReplayVerificationError
        return validated


def adjudicate_variant_peptide_discrepancy_queue(
    request: object,
) -> VariantPeptideAdjudicationResult:
    """Public provisional M17-06 adjudication operation."""

    return M1706AdjudicationEngine().export(request)


__all__ = [
    "M1706AdjudicationEngine",
    "M1706AuthorizationError",
    "M1706ExportError",
    "M1706ReplayVerificationError",
    "adjudicate_variant_peptide_discrepancy_queue",
    "preflight_adjudication_authorization",
]
