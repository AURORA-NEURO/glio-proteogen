"""Runtime and adversarial coverage for provisional M18-06 adjudication."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m18_06 import (
    AdjudicateBiomarkerPanelQueueRequest,
    DiscrepancyQueueEntry,
    DiscrepancyReasonCode,
    DiscrepancySeverity,
    QueueEntryState,
    QueueFindingCode,
    QueueResultStatus,
    ReviewDecision,
    ReviewerAssignment,
    ReviewWorkspaceConfiguration,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_06_reviewer_adjudication as m1806,
)

ROUTINE_REVIEWER_TOKEN = "reviewer.token.routine"  # noqa: S105
CRITICAL_REVIEWER_TOKEN = "reviewer.token.critical"  # noqa: S105
EXPECTED_HISTORY_EVENTS = 4


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m1806:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Synthetic caller-declared M18-06 review evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
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
        request_id="request.synthetic.m1806",
        actor_id="actor.synthetic.m1806",
        occurred_at=datetime(2026, 8, 15, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m1806.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _request(
    *,
    entry_state: QueueEntryState = QueueEntryState.RESOLVED,
    critical_state: QueueEntryState | None = None,
    decision: ReviewDecision = ReviewDecision.ACCEPT,
    assignments_complete: bool = True,
    upstream_media_type: str = "application/vnd.glio-proteogen.m18-05+json",
) -> AdjudicateBiomarkerPanelQueueRequest:
    evidence = (_evidence(_artifact("review")),)
    effective_critical_state = critical_state or entry_state
    entries = (
        DiscrepancyQueueEntry(
            discrepancy_id="discrepancy.routine",
            reason_code=DiscrepancyReasonCode.SOURCE_DISAGREEMENT,
            severity=DiscrepancySeverity.ROUTINE,
            description="Synthetic routine discrepancy.",
            state=entry_state,
            evidence=evidence,
        ),
        DiscrepancyQueueEntry(
            discrepancy_id="discrepancy.critical",
            reason_code=DiscrepancyReasonCode.QUALITY_FAILURE,
            severity=DiscrepancySeverity.CRITICAL,
            description="Synthetic critical discrepancy.",
            state=effective_critical_state,
            evidence=evidence,
        ),
    )
    assignments = [
        ReviewerAssignment(
            assignment_id="assignment.routine",
            discrepancy_id="discrepancy.routine",
            reviewer_role="independent reviewer",
            reviewer_token=ROUTINE_REVIEWER_TOKEN,
            decision=decision,
            rationale="Synthetic blinded decision.",
            evidence=evidence,
        )
    ]
    if assignments_complete:
        assignments.append(
            ReviewerAssignment(
                assignment_id="assignment.critical",
                discrepancy_id="discrepancy.critical",
                reviewer_role="senior reviewer",
                reviewer_token=CRITICAL_REVIEWER_TOKEN,
                decision=decision,
                rationale="Synthetic blinded decision.",
                evidence=evidence,
            )
        )
    return AdjudicateBiomarkerPanelQueueRequest(
        request_id="request.synthetic.m1806",
        context=_context(),
        upstream_result=_artifact("upstream", upstream_media_type),
        entries=entries,
        assignments=tuple(assignments),
        configuration=ReviewWorkspaceConfiguration(
            configuration_id="configuration.synthetic.m1806",
            version="1.0.0",
            maximum_queue_entries=256,
            evidence=evidence,
        ),
        source_artifacts=(_artifact("source-manifest"),),
    )


def test_resolved_queue_records_blinded_immutable_history_and_replays() -> None:
    result = m1806.M1806Engine().adapt(_request())

    assert result.status is QueueResultStatus.RECORDED
    assert result.record is not None
    assert result.record.status.value == "resolved"
    assert len(result.record.history) == EXPECTED_HISTORY_EVENTS
    assert result.record.history[-1].actor_token == CRITICAL_REVIEWER_TOKEN
    assert result.record.locked is True
    assert result.parent_target == "biomarker panel"
    assert result.emits_parent is False
    assert m1806.M1806Engine().replay(result) == result


def test_deferred_critical_review_records_escalation() -> None:
    result = m1806.M1806Engine().adapt(
        _request(entry_state=QueueEntryState.IN_REVIEW, decision=ReviewDecision.DEFER)
    )

    assert result.status is QueueResultStatus.RECORDED
    assert result.record is not None
    assert result.record.status.value == "escalated"
    assert result.record.resolution_summary is None
    assert any(item.code is QueueFindingCode.CRITICAL_UNRESOLVED for item in result.findings)
    assert result.human_review_required is True


def test_missing_assignment_abstains_without_record() -> None:
    result = m1806.M1806Engine().adapt(_request(assignments_complete=False))

    assert result.status is QueueResultStatus.ABSTAINED
    assert result.record is None
    assert any(item.code is QueueFindingCode.ASSIGNMENT_MISSING for item in result.findings)
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_not_evaluable_queue_abstains() -> None:
    result = m1806.M1806Engine().adapt(_request(entry_state=QueueEntryState.NOT_EVALUABLE))

    assert result.status is QueueResultStatus.ABSTAINED
    assert result.record is None
    assert any(item.code is QueueFindingCode.HISTORY_INCOMPLETE for item in result.findings)


def test_control_denial_precedes_queue_traversal() -> None:
    request = _request().model_copy(
        update={
            "context": _context().model_copy(
                update={
                    "references": _context().references.model_copy(
                        update={
                            "consent": _context().references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )

    with pytest.raises(m1806.M1806AuthorizationError, match="consent"):
        m1806.M1806Engine().adapt(request)


def test_upstream_media_type_is_strict() -> None:
    with pytest.raises(ValueError, match="M18-05"):
        m1806.M1806Engine().adapt(_request(upstream_media_type="application/json"))


def test_tampered_result_digest_is_rejected() -> None:
    result = m1806.M1806Engine().adapt(_request())
    tampered = result.model_copy(update={"human_review_required": False})

    with pytest.raises(m1806.M1806ReplayError, match="payload digest"):
        m1806.M1806Engine().replay(tampered)


def test_plugin_capability_and_direct_run_snapshots_are_instance_bound() -> None:
    first = m1806.M1806Plugin()
    second = m1806.M1806Plugin()
    token = first.validate(_request())

    assert first.run(token).status is QueueResultStatus.RECORDED
    with pytest.raises(TypeError, match="validated request token"):
        second.run(token)

    forged = m1806.ValidatedM1806Request(token.request, object())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(forged)

    replaced = first.validate(_request())
    object.__setattr__(replaced, "request", replaced.request.model_copy())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(replaced)

    validated = first.validate_request(_request())
    object.__setattr__(validated.entries[0], "description", "forged discrepancy")
    with pytest.raises(TypeError, match="unchanged validated request"):
        first.run(validated)
