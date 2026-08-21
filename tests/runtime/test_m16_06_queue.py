"""Runtime and replay tests for the M16-06 adjudication queue."""

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m16_06 import (
    M1606_M1605_INPUT_MEDIA_TYPE,
    AdjudicateProteinRnaDiscordanceQueueRequest,
    DiscrepancyQueueEntry,
    DiscrepancyReasonCode,
    DiscrepancySeverity,
    QueueEntryState,
    QueueFinding,
    QueueFindingCode,
    ReviewDecision,
    ReviewerAssignment,
    ReviewWorkspaceConfiguration,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c16_kinophos_object_consumer import (
    M1606AuthorizationError,
    M1606Engine,
    M1606Plugin,
    M1606ReplayError,
    M1606Service,
    adjudicate_protein_rna_discordance_queue,
)

_DIGEST = "sha256:" + "1" * 64


def _artifact(
    name: str,
    media_type: str = "application/vnd.glio.evidence+json",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _decision(name: str, state: UpstreamDecisionState) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=state,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{name}"),
    )


def _context(consent: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    return ExecutionContext(
        request_id="context.request",
        actor_id="actor.reviewer",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", UpstreamDecisionState.ACCEPTED),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=_artifact("evidence.identity"),
            ),
            provenance=_decision("provenance", UpstreamDecisionState.ACCEPTED),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=_artifact("evidence.consent"),
            ),
            quality=_decision("quality", UpstreamDecisionState.ACCEPTED),
            support=_decision("support", UpstreamDecisionState.ACCEPTED),
            intended_use=_decision("intended", UpstreamDecisionState.ACCEPTED),
        ),
    )


def _evidence(name: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(name),
            role="evidence",
            claim="Caller-declared discrepancy evidence.",
        ),
    )


def _request(
    *,
    decision: ReviewDecision = ReviewDecision.ACCEPT,
    severity: DiscrepancySeverity = DiscrepancySeverity.MATERIAL,
    consent: ConsentState = ConsentState.GRANTED,
    duplicate: bool = False,
) -> AdjudicateProteinRnaDiscordanceQueueRequest:
    entry = DiscrepancyQueueEntry(
        discrepancy_id="discrepancy.one",
        reason_code=DiscrepancyReasonCode.SOURCE_DISAGREEMENT,
        severity=severity,
        description="Protein and RNA evidence require reviewer adjudication.",
        state=QueueEntryState.QUEUED,
        evidence=_evidence("evidence.discrepancy"),
    )
    assignment = ReviewerAssignment(
        assignment_id="assignment.one",
        discrepancy_id="discrepancy.one",
        reviewer_role="quality_reviewer",
        reviewer_token="reviewer.opaque",  # noqa: S106
        decision=decision,
        rationale="The reviewer recorded an explicit, blinded decision.",
        evidence=_evidence("evidence.assignment"),
    )
    entries = (entry, entry) if duplicate else (entry,)
    return AdjudicateProteinRnaDiscordanceQueueRequest(
        request_id="request.m1606.001",
        context=_context(consent),
        upstream_result=_artifact("upstream.workspace", M1606_M1605_INPUT_MEDIA_TYPE),
        entries=entries,
        assignments=(assignment,),
        configuration=ReviewWorkspaceConfiguration(
            configuration_id="config.m1606",
            version="1.0.0",
            maximum_queue_entries=256,
        ),
        source_artifacts=(_artifact("source.review"),),
    )


def test_resolved_queue_preserves_history_and_replays() -> None:
    result = M1606Engine().adjudicate(_request(severity=DiscrepancySeverity.CRITICAL))
    assert result.status.value == "recorded"
    assert result.record is not None
    assert result.record.locked is True
    assert result.record.history[0].actor_token == "reviewer.opaque"  # noqa: S105
    assert result.emits_parent is False
    assert M1606Engine().replay(result) == result


def test_deferred_review_abstains_without_record() -> None:
    result = M1606Engine().adjudicate(_request(decision=ReviewDecision.DEFER))
    assert result.status.value == "abstained"
    assert result.record is None
    assert result.human_review_required is True
    assert result.support_decision.status.value == "review_required"


def test_denied_consent_is_rejected_before_queue_traversal() -> None:
    with pytest.raises(M1606AuthorizationError, match="consent"):
        M1606Engine().adjudicate(_request(consent=ConsentState.WITHHELD))


def test_duplicate_discrepancy_is_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        M1606Engine().adjudicate(_request(duplicate=True))


def test_tampered_result_digest_is_rejected() -> None:
    result = M1606Engine().adjudicate(_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "2" * 64})
    with pytest.raises(M1606ReplayError, match="digest"):
        M1606Engine().replay(tampered)


def test_self_rehashed_semantic_mutation_is_rejected() -> None:
    result = M1606Engine().adjudicate(_request())
    finding = QueueFinding(
        finding_id="finding.forged",
        code=QueueFindingCode.REVIEW_REQUIRED,
        message="Forged semantic finding.",
        evidence=result.evidence,
    )
    mutated = result.model_copy(
        update={"findings": (finding,), "result_digest": "sha256:" + "0" * 64}
    )
    mutated = mutated.model_copy(
        update={"result_digest": result_payload_digest(mutated)}
    )
    with pytest.raises(M1606ReplayError, match="semantic"):
        M1606Engine().replay(mutated)


def test_missing_controls_fail_before_traversal() -> None:
    with pytest.raises(M1606AuthorizationError, match="seven upstream controls"):
        M1606Engine().adjudicate({"context": {}})


def test_missing_assignment_abstains_explicitly() -> None:
    request = _request()
    second = request.entries[0].model_copy(update={"discrepancy_id": "discrepancy.two"})
    incomplete = request.model_copy(update={"entries": (request.entries[0], second)})
    result = M1606Engine().adjudicate(incomplete)
    assert result.status.value == "abstained"
    assert result.findings[0].code.value == "assignment_missing"


def test_request_digest_and_facades_are_sealed() -> None:
    engine = M1606Engine()
    result = engine.adjudicate(_request())
    tampered_request = result.model_copy(update={"request_digest": "sha256:" + "3" * 64})
    with pytest.raises(M1606ReplayError, match="request digest"):
        engine.replay(tampered_request)
    plugin = M1606Plugin()
    assert plugin.descriptor.blinded_review is True
    assert plugin.descriptor.kinase_activity is False
    validated = plugin.validate_request(_request())
    assert plugin.replay(plugin.run(validated)).status.value == "recorded"
    service = M1606Service()
    assert service.validate_request(_request()).request_id == "request.m1606.001"
    assert service.replay(service.adjudicate(_request())).status.value == "recorded"
    assert adjudicate_protein_rna_discordance_queue(_request()).status.value == "recorded"
