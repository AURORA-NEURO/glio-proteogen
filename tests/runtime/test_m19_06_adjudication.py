"""Runtime, replay, and ownership gates for M19-06."""

import pytest

from glio_proteogen.contracts.m19_06 import QueueEntryState, QueueResultStatus, ReviewDecision
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_06_reviewer_adjudication import (
    M1906AuthorizationError,
    M1906Engine,
    M1906Plugin,
    M1906ReplayError,
)
from tests.contract.test_m19_06_provisional import _assignment, _entry, _request

_ZERO_DIGEST = "sha256:" + "0" * 64


def test_resolved_queue_emits_chained_record_and_exact_replay() -> None:
    result = M1906Engine().adapt(_request())
    assert result.status is QueueResultStatus.RECORDED
    assert result.record is not None
    assert result.record.status.value == "resolved"
    assert result.record.history[0].previous_event_digest is None
    assert all(
        current.previous_event_digest == previous.event_digest
        for previous, current in zip(result.record.history, result.record.history[1:], strict=False)
    )
    assert result.record.history[-1].event_type.value == "resolved"
    assert M1906Engine().replay(result) == result


def test_unresolved_queue_abstains_without_promoting_a_record() -> None:
    entry = _entry(state=QueueEntryState.IN_REVIEW)
    request = _request(
        entries=(entry,),
        assignments=(
            _assignment(
                discrepancy_id=entry.discrepancy_id,
                decision=ReviewDecision.DEFER,
            ),
        ),
    )
    result = M1906Engine().adapt(request)
    assert result.status is QueueResultStatus.ABSTAINED
    assert result.record is None
    assert result.abstention_reason is not None
    assert result.support_decision.status.value == "review_required"


def test_missing_or_rejected_control_fails_before_queue_traversal() -> None:
    with pytest.raises(M1906AuthorizationError, match="all seven"):
        M1906Engine().validate_request({"context": {}})
    payload = _request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    with pytest.raises(M1906AuthorizationError, match="consent"):
        M1906Engine().validate_request(payload)


def test_replay_rejects_request_and_result_tampering() -> None:
    result = M1906Engine().adapt(_request())
    tampered_request = result.model_copy(update={"request_digest": _ZERO_DIGEST})
    with pytest.raises(M1906ReplayError, match="request digest"):
        M1906Engine().replay(tampered_request)
    tampered_result = result.model_copy(update={"result_digest": _ZERO_DIGEST})
    with pytest.raises(M1906ReplayError, match="payload digest"):
        M1906Engine().replay(tampered_result)


def test_plugin_descriptor_and_runtime_are_bounded() -> None:
    plugin = M1906Plugin()
    result = plugin.run(_request())
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M19-06"
    assert plugin.descriptor.parent_target == "proteotype"
    assert plugin.descriptor.kinase_activity is False
    assert plugin.descriptor.treatment_recommendation is False
    assert plugin.replay(result) == result
