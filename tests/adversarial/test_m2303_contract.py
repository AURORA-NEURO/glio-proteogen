"""Adversarial contract and replay cases for provisional M23-03."""

from __future__ import annotations

from math import inf

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m23_03 import (
    BenchmarkDossier,
    ComputeMatchedComparison,
    canonical_request_digest,
    result_identifier,
)
from tests.contract.test_m23_03_hardening import _dossier, _request


def test_request_replay_digest_changes_for_nested_benchmark_tamper() -> None:
    request = _request()
    baseline = request.baseline_runs[0]
    tampered = request.model_copy(
        update={
            "baseline_runs": (
                baseline.model_copy(
                    update={
                        "metrics": (
                            baseline.metrics[0].model_copy(update={"candidate_value": 0.9}),
                        )
                    },
                ),
                *request.baseline_runs[1:],
            )
        }
    )
    assert canonical_request_digest(tampered) != canonical_request_digest(request)
    assert result_identifier(tampered) != result_identifier(request)


def test_duplicate_upstream_source_is_rejected_before_runtime() -> None:
    request = _request()
    upstream = request.upstream_result
    with pytest.raises(ValidationError, match="source artifacts must be unique"):
        request.__class__.model_validate(
            request.model_dump(mode="python") | {"source_artifacts": (upstream, upstream)},
            strict=True,
        )


def test_cross_scope_dossier_identifier_collision_is_rejected() -> None:
    dossier = _dossier()
    with pytest.raises(ValidationError, match="dossier metric"):
        BenchmarkDossier.model_validate(
            dossier.model_dump(mode="python") | {"metrics": (dossier.baselines[0].metrics[0],)},
            strict=True,
        )


def test_compute_matching_rejects_nonfinite_and_unknown_run_references() -> None:
    comparison = _dossier().comparisons[0]
    with pytest.raises(ValidationError, match=r"finite|Input should be a valid number"):
        ComputeMatchedComparison.model_validate(
            comparison.model_dump(mode="python") | {"reference_score": inf}, strict=True
        )
    with pytest.raises(ValidationError, match="declared baseline"):
        BenchmarkDossier.model_validate(
            _dossier().model_dump(mode="python")
            | {
                "comparisons": (comparison.model_copy(update={"reference_run_id": "not-declared"}),)
            },
            strict=True,
        )


def test_ablation_replay_does_not_accept_a_forged_delta() -> None:
    ablation = _dossier().ablations[0]
    with pytest.raises(ValidationError, match="score delta"):
        ablation.__class__.model_validate(
            ablation.model_dump(mode="python") | {"score_delta": 99.0}, strict=True
        )


__all__ = []
