"""M08-03 baseline lifecycle, abstention, replay, and plugin tests."""

from __future__ import annotations

import pytest
from evals.m08_03.evaluator import evaluate_all
from evals.m08_03.fixtures import request

from glio_proteogen.contracts.m08_03 import BaselineEstimateStatus, BaselineFeatureState
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator import (
    M0803Plugin,
    M0803Service,
)

EXPECTED_SCENARIOS = 4


def test_transparent_baseline_estimates_and_replays() -> None:
    service = M0803Service()
    candidate = request()
    result = service.execute(candidate)
    assert result.status is BaselineEstimateStatus.ESTIMATED
    assert result.estimate is not None
    assert service.replay(candidate, result).result_digest == result.result_digest


def test_missing_features_abstain_without_estimate() -> None:
    result = M0803Service().execute(
        request(feature_state=BaselineFeatureState.MISSING)
    )
    assert result.status is BaselineEstimateStatus.ABSTAINED
    assert result.estimate is None
    assert result.human_review_required


def test_unsupported_source_abstains() -> None:
    result = M0803Service().execute(request(source_name="source.unsupported.ood"))
    assert result.status is BaselineEstimateStatus.ABSTAINED
    assert result.findings


def test_plugin_json_and_typed_parity_and_forgery() -> None:
    service = M0803Service()
    plugin = M0803Plugin(service)
    typed = plugin.run(plugin.validate(request()))
    encoded = canonical_json_bytes(request().model_dump(mode="json"))
    decoded = plugin.run(plugin.validate(encoded))
    assert decoded.model_dump(mode="json") == typed.model_dump(mode="json")
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_evaluator_matrix_passes() -> None:
    records = evaluate_all()
    assert len(records) == EXPECTED_SCENARIOS
    assert all(record.passed for record in records)
