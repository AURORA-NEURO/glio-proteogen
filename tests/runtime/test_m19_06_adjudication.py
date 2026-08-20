"""Runtime, replay, and ownership gates for M19-06."""

import pytest

from glio_proteogen.contracts.m19_06 import (
    QueueEntryState,
    QueueResultStatus,
    ReviewDecision,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import EvidenceReference
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


def test_provenance_binds_nested_review_evidence_artifact_identity() -> None:
    request = _request()

    def with_digest(evidence: EvidenceReference, label: str) -> EvidenceReference:
        reference = evidence.reference.model_copy(
            update={
                "artifact_id": f"artifact.{label}",
                "digest": sha256_digest(label),
            }
        )
        return evidence.model_copy(update={"reference": reference})

    entry = request.entries[0].model_copy(
        update={"evidence": (with_digest(request.entries[0].evidence[0], "entry"),)}
    )
    assignment = request.assignments[0].model_copy(
        update={"evidence": (with_digest(request.assignments[0].evidence[0], "assignment"),)}
    )
    configuration = request.configuration.model_copy(
        update={"evidence": (with_digest(request.entries[0].evidence[0], "configuration"),)}
    )
    bound_request = request.model_copy(
        update={
            "entries": (entry,),
            "assignments": (assignment,),
            "configuration": configuration,
        }
    )

    result = M1906Engine().adapt(bound_request)
    input_digests = set(result.provenance.input_digests)
    assert canonical_request_digest(bound_request) in input_digests
    assert all(
        digest in input_digests
        for digest in (
            entry.evidence[0].reference.digest,
            assignment.evidence[0].reference.digest,
            configuration.evidence[0].reference.digest,
        )
    )


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
