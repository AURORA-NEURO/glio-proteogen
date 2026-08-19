"""Focused runtime, plugin, and replay coverage for M20-06."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m20_06 import QueueEntryState, ReviewDecision
from glio_proteogen.contracts.m20_06.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c20_biomarker_panel.m20_06_reviewer_discrepancy_adjudication import (
    AdjudicationSubmission,
    M2006AuthorizationError,
    M2006Engine,
    M2006Plugin,
    M2006ReplayError,
    M2006Service,
    ValidatedM2006Request,
)
from tests.contract.test_m20_06_adversarial import _assignment, _entry, _request


def test_resolved_queue_records_immutable_history_and_replays() -> None:
    engine = M2006Engine()
    result = engine.adjudicate(_request())
    assert result.status.value == "recorded"
    assert result.record is not None
    assert tuple(event.sequence for event in result.record.history) == (1, 2, 3, 4)
    assert engine.replay(result) == result


def test_deferred_queue_abstains_without_record() -> None:
    request = _request()
    entry = _entry(state=QueueEntryState.IN_REVIEW)
    deferred = _assignment(entry, decision=ReviewDecision.DEFER)
    result = M2006Engine().adjudicate(
        request.model_copy(update={"entries": (entry,), "assignments": (deferred,)})
    )
    assert result.status.value == "abstained"
    assert result.record is None
    assert result.abstention_reason is not None
    assert result.support_decision.status.value == "review_required"


def test_control_denial_precedes_queue_traversal() -> None:
    request = _request()
    denied = request.context.references.consent.model_copy(update={"state": ConsentState.WITHHELD})
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"consent": denied})}
    )
    with pytest.raises(M2006AuthorizationError, match="consent"):
        M2006Engine().adjudicate(request.model_copy(update={"context": context}))


def test_plugin_requires_submission_and_preserves_parse_once_boundary() -> None:
    plugin = M2006Plugin(M2006Service())
    request = _request()
    validated = plugin.validate(AdjudicationSubmission(canonical_json_bytes(request)))
    assert plugin.run(validated).status.value == "recorded"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M20-06"
    with pytest.raises(TypeError, match="submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request"):
        plugin.run(request)  # type: ignore[arg-type]


def test_plugin_rejects_forged_cross_instance_and_nested_mutated_tokens() -> None:
    request = _request()
    service = M2006Service()
    plugin = M2006Plugin(service)
    other = M2006Plugin(service)
    token = plugin.validate(AdjudicationSubmission(request))
    forged = ValidatedM2006Request(request=token.request, _seal=object())

    with pytest.raises(TypeError, match="validated request"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request"):
        other.run(token)

    changed_entry = token.request.entries[0].model_copy(
        update={"description": "forged discrepancy description"}
    )
    object.__setattr__(
        token.request,
        "entries",
        (changed_entry, *token.request.entries[1:]),
    )
    with pytest.raises(TypeError, match="validated request"):
        plugin.run(token)


def test_service_replay_rejects_tampered_payload() -> None:
    service = M2006Service()
    result = service.adjudicate(_request())
    assert service.replay(result) == result
    assert result.record is not None
    tampered_record = result.record.model_copy(update={"resolution_summary": "tampered"})
    tampered = result.model_copy(update={"record": tampered_record})
    with pytest.raises(M2006ReplayError, match="payload digest"):
        service.replay(tampered)


def test_service_replay_rejects_self_rehashed_semantic_mutation() -> None:
    service = M2006Service()
    result = service.adjudicate(_request())
    limitation = result.limitations[0].model_copy(update={"statement": "tampered"})
    tampered = result.model_copy(update={"limitations": (limitation, *result.limitations[1:])})
    forged = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises(M2006ReplayError, match="deterministic replay"):
        service.replay(forged)


def test_not_evaluable_queue_abstains_safely() -> None:
    request = _request()
    entry = _entry(state=QueueEntryState.NOT_EVALUABLE)
    assignment = _assignment(entry, decision=ReviewDecision.ABSTAIN)
    result = M2006Engine().adjudicate(
        request.model_copy(update={"entries": (entry,), "assignments": (assignment,)})
    )
    assert result.status.value == "abstained"
    assert any(item.code.value == "history_incomplete" for item in result.findings)


def test_missing_assignment_abstains_without_fabricating_review() -> None:
    request = _request()
    entry = _entry().model_copy(update={"state": QueueEntryState.IN_REVIEW})
    # Contract validation rejects an empty assignment tuple; use a different entry
    # with a valid assignment and retain a second unassigned entry.
    second = _entry("second", state=QueueEntryState.IN_REVIEW)
    result = M2006Engine().adjudicate(request.model_copy(update={"entries": (entry, second)}))
    assert result.status.value == "abstained"
    assert any(item.code.value == "assignment_missing" for item in result.findings)
