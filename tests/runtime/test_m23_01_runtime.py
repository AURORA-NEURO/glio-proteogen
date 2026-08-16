"""Runtime, authorization, abstention, and replay tests for M23-01."""

from typing import Any, cast

import pytest

from glio_proteogen.contracts.m23_01 import (
    AdjudicationStatus,
    CurationStatus,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c21_reference_material.m23_01_reference_truth_benchmark_curator import (
    M2301AuthorizationError,
    M2301ReferenceTruthBenchmarkCurator,
    M2301ReplayError,
    M2301Service,
    preflight_m2301_authorization,
)
from tests.contract.test_m23_01_deep import _request


def test_curates_locked_package_and_replays_exactly() -> None:
    request = _request()
    service = M2301Service()
    result = service.execute(request)
    assert result.status is CurationStatus.CURATED
    assert result.package is not None
    assert result.package.locked is True
    assert service.verify_replay(result) == result


def test_pending_or_rejected_included_material_abstains_safely() -> None:
    request = _request()
    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.PENDING})
    pending_request = request.model_copy(
        update={"adjudications": (pending, *request.adjudications[1:])}
    )
    pending_result = M2301Service().execute(pending_request)
    assert pending_result.status is CurationStatus.ABSTAINED
    assert pending_result.package is None
    assert pending_result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    rejected = request.adjudications[0].model_copy(
        update={
            "status": AdjudicationStatus.REJECTED,
            "disagreement_statement": "Reviewers did not agree on the label.",
        }
    )
    rejected_request = request.model_copy(
        update={"adjudications": (rejected, *request.adjudications[1:])}
    )
    rejected_result = M2301Service().execute(rejected_request)
    assert rejected_result.status is CurationStatus.ABSTAINED
    assert rejected_result.package is None


def test_denied_controls_fail_before_validation_or_traversal() -> None:
    request = _request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": "withheld"}
                    )
                }
            )
        }
    )
    denied = request.model_copy(update={"context": denied_context})
    with pytest.raises(M2301AuthorizationError):
        preflight_m2301_authorization(denied.model_dump(mode="python"))
    with pytest.raises(M2301AuthorizationError):
        M2301Service().execute(denied)
    with pytest.raises(M2301AuthorizationError):
        preflight_m2301_authorization({"context": {"references": {}}})


def test_replay_rejects_tampered_result() -> None:
    result = M2301Service().execute(_request())
    tampered = result.model_copy(update={"result_id": "tampered-result"})
    with pytest.raises(M2301ReplayError):
        M2301ReferenceTruthBenchmarkCurator().verify_replay(tampered)


def test_hostile_candidate_types_fail_closed() -> None:
    with pytest.raises(M2301AuthorizationError):
        preflight_m2301_authorization(cast("Any", object()))
