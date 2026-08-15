"""M08-03 baseline lifecycle, abstention, replay, and plugin tests."""

from __future__ import annotations

import pytest
from evals.m08_03.benchmark import measure
from evals.m08_03.evaluator import evaluate_all, evaluate_replay_and_tamper
from evals.m08_03.fixtures import request

from glio_proteogen.contracts.m08_03 import (
    BaselineEstimateStatus,
    BaselineFeatureState,
    BaselineMethod,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator import (
    M0803Plugin,
    M0803Service,
)

EXPECTED_SCENARIOS = 6


def test_transparent_baseline_estimates_and_replays() -> None:
    service = M0803Service()
    candidate = request()
    result = service.execute(candidate)
    assert result.status is BaselineEstimateStatus.ESTIMATED
    assert result.estimate is not None
    assert service.replay(candidate, result).result_digest == result.result_digest


def test_missing_features_abstain_without_estimate() -> None:
    result = M0803Service().execute(request(feature_state=BaselineFeatureState.MISSING))
    assert result.status is BaselineEstimateStatus.ABSTAINED
    assert result.estimate is None
    assert result.human_review_required


def test_unsupported_source_abstains() -> None:
    result = M0803Service().execute(request(source_name="source.unsupported.ood"))
    assert result.status is BaselineEstimateStatus.ABSTAINED
    assert result.findings


@pytest.mark.parametrize(
    "method",
    tuple(BaselineMethod),
)
def test_declared_architecture_changes_only_the_deterministic_signal(
    method: BaselineMethod,
) -> None:
    candidate = request()
    configured = candidate.configuration.model_copy(update={"method": method})
    result = M0803Service().execute(candidate.model_copy(update={"configuration": configured}))
    assert result.status is BaselineEstimateStatus.ESTIMATED
    assert result.estimate is not None
    assert 0.0 <= result.estimate.score <= 1.0
    assert result.provenance.input_digests == (
        candidate.representation_result.digest,
        *(artifact.digest for artifact in candidate.source_artifacts),
        result.request_digest,
    )


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
    assert evaluate_replay_and_tamper()


def test_benchmark_requires_positive_iterations() -> None:
    with pytest.raises(ValueError, match="iterations must be positive"):
        measure(0)
