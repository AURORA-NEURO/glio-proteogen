"""Runtime, replay, control, and abstention tests for M25-01."""

from __future__ import annotations

import pytest
from evals.m25_01.fixture import (
    build_request,
    denied_request,
    pending_request,
    rejected_included_request,
)

from glio_proteogen.contracts.m25_01 import CurationStatus
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c21_reference_material.m25_01_reference_truth_benchmark_curator import (
    M2501AuthorizationError,
    M2501ReferenceTruthBenchmarkCurator,
    M2501ReplayError,
)


def test_curated_result_contains_locked_package_and_replay_closure() -> None:
    engine = M2501ReferenceTruthBenchmarkCurator()
    result = engine.curate(build_request())

    assert result.status is CurationStatus.CURATED
    assert result.package is not None
    assert result.package.locked is True
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False
    assert engine.verify_replay(result) == result


def test_pending_adjudication_abstains_without_package() -> None:
    result = M2501ReferenceTruthBenchmarkCurator().curate(pending_request())

    assert result.status is CurationStatus.ABSTAINED
    assert result.package is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.abstention_reason is not None
    assert any(finding.code.value == "adjudication_pending" for finding in result.findings)


def test_rejected_included_reference_abstains_with_lock_finding() -> None:
    result = M2501ReferenceTruthBenchmarkCurator().curate(rejected_included_request())

    assert result.status is CurationStatus.ABSTAINED
    assert result.package is None
    assert any(finding.code.value == "lock_incomplete" for finding in result.findings)


def test_denied_control_fails_before_request_validation() -> None:
    with pytest.raises(M2501AuthorizationError, match="requires accepted"):
        M2501ReferenceTruthBenchmarkCurator().curate(denied_request())


def test_hostile_mapping_fails_closed() -> None:
    with pytest.raises(M2501AuthorizationError):
        M2501ReferenceTruthBenchmarkCurator().curate({"context": {"references": {}}})


def test_replay_rejects_result_tampering() -> None:
    engine = M2501ReferenceTruthBenchmarkCurator()
    result = engine.curate(build_request())
    tampered = result.model_copy(update={"result_id": "result-tampered"})

    with pytest.raises(M2501ReplayError):
        engine.verify_replay(tampered)


def test_replay_rejects_nested_request_tampering() -> None:
    engine = M2501ReferenceTruthBenchmarkCurator()
    result = engine.curate(build_request())
    request = result.request.model_copy(update={"request_id": "changed-request"})
    tampered = result.model_copy(update={"request": request})

    with pytest.raises(M2501ReplayError):
        engine.verify_replay(tampered)
