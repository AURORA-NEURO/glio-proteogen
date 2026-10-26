"""Paired numerical and abstention checks for the versioned 240-iteration audit."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    continuation,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    model as legacy,
)

DIGEST = "sha256:" + "7" * 64
PATIENTS = 96
FOLDS = 5
REPLICATES = 128
REQUIRED = 103
ITERATIONS = 240
LEGACY_ITERATIONS = 30
LEGACY_SLOW_SUCCESSES = 126
INTERVAL_COVERAGE = 0.9


def _gene(seed: int = 7_103) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    random = np.random.default_rng(seed)
    cnv = random.normal(size=96)
    rna = 0.75 * cnv + random.normal(0.0, 0.35, 96)
    protein = 1.15 * rna + 0.10 * cnv + random.normal(0.0, 0.20, 96)
    return cnv, rna, protein, (np.arange(96) % 5).astype(np.int8)


@pytest.fixture(scope="module")
def paired_oracle() -> tuple[
    tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    legacy.TranscriptProteinDiscordanceDevelopmentFit,
    continuation.ContinuationGeneResult,
    continuation.ContinuationGeneResult,
]:
    values = _gene()
    old = legacy.fit_transcript_protein_discordance_gene(*values, request_digest=DIGEST)
    assert old is not None
    thirty = continuation._fit_continuation_gene_for_budget(
        *values,
        request_digest=DIGEST,
        budget=30,
    )
    extended = continuation.fit_continuation_gene(*values, request_digest=DIGEST)
    return values, old, thirty, extended


def test_private_thirty_budget_oracle_preserves_the_entire_accepted_legacy_summary(
    paired_oracle: tuple[Any, ...],
) -> None:
    _values, old, thirty, _extended = paired_oracle
    assert thirty.accepted
    assert thirty.summary is not None
    assert asdict(thirty.summary) == asdict(old.summary)
    assert thirty.point_folds == old.fold_trace
    assert thirty.comparison_bootstrap_seed == old.summary.bootstrap.seed
    assert thirty.bootstrap_successful == old.summary.bootstrap.replicates_successful
    assert thirty.bootstrap_attempted == thirty.bootstrap_requested == REPLICATES


def _assert_no_arrays(value: object) -> None:
    assert not isinstance(value, np.ndarray)
    if isinstance(value, dict):
        assert not {"transient_oof", "predictions", "observed_protein", "pattern"}.intersection(
            value
        )
        for nested in value.values():
            _assert_no_arrays(nested)
    elif isinstance(value, (list, tuple)):
        assert len(value) != PATIENTS
        for nested in value:
            _assert_no_arrays(nested)


def test_public_continuation_returns_genuine_uncertainty_and_only_aggregate_evidence(
    paired_oracle: tuple[Any, ...],
) -> None:
    _values, old, _thirty, result = paired_oracle
    assert result.profile_id == "cptac-gbm-transcript-protein-continuation/1.0.0"
    assert result.budget == ITERATIONS
    assert result.accepted
    assert result.profile_digest.startswith("sha256:")
    assert result.point_valid_folds == FOLDS
    assert result.point_oof_patient_groups == PATIENTS
    assert result.bootstrap_requested == result.bootstrap_attempted == REPLICATES
    assert REQUIRED <= result.bootstrap_successful <= REPLICATES
    assert result.bootstrap_required == REQUIRED
    assert result.failure_reason is None
    summary = result.summary
    assert summary is not None
    assert summary.bootstrap.full_model_r2.lower < summary.bootstrap.full_model_r2.upper
    assert (
        summary.bootstrap.conditional_rna_slope.lower
        < summary.bootstrap.conditional_rna_slope.upper
    )
    assert summary.bootstrap.seed == result.comparison_bootstrap_seed == old.summary.bootstrap.seed
    assert result.comparison_request_digest == DIGEST
    assert result.comparison_seed_context.endswith("discordance|patient-bootstrap-v1")
    assert summary.bootstrap.full_model_r2.confidence_level == INTERVAL_COVERAGE
    _assert_no_arrays(asdict(result))
    assert json.loads(json.dumps(asdict(result)))["accepted"] is True


def test_row_permutation_is_deterministic_and_does_not_mutate_input_or_legacy_policy(
    paired_oracle: tuple[Any, ...],
) -> None:
    values, _old, _thirty, result = paired_oracle
    snapshots = tuple(value.tobytes() for value in values)
    order = np.random.default_rng(191).permutation(96)
    permuted = tuple(value[order] for value in values)
    replay = continuation.fit_continuation_gene(*permuted, request_digest=DIGEST)
    assert asdict(replay) == asdict(result)
    assert tuple(value.tobytes() for value in values) == snapshots
    assert legacy.DiscordanceFitConfiguration().bootstrap_replicates == REPLICATES
    assert legacy.fit_huber.__module__ == "glio_proteogen.research.cptac_gbm_cis_dosage.model"


def test_insufficient_complete_case_support_abstains_before_any_bootstrap() -> None:
    cnv, rna, protein, folds = _gene()
    protein[:50] = np.nan
    result = continuation.fit_continuation_gene(cnv, rna, protein, folds, request_digest=DIGEST)
    assert not result.accepted
    assert result.summary is None
    assert result.point_valid_folds == result.point_oof_patient_groups == 0
    assert result.bootstrap_requested == REPLICATES
    assert result.bootstrap_attempted == result.bootstrap_successful == 0
    assert result.failure_reason is not None
    assert "point fit" in result.failure_reason
    assert len(result.point_folds) == FOLDS
    assert all(not trace.valid for trace in result.point_folds)


@pytest.mark.parametrize("successful", [102, 103])
def test_exact_103_gate_and_same_legacy_pcg_draws_without_resorting_bootstrap_rows(
    monkeypatch: pytest.MonkeyPatch,
    paired_oracle: tuple[Any, ...],
    successful: int,
) -> None:
    values, _old, _thirty, _extended = paired_oracle
    order = legacy._canonical_row_order(*values)
    canonical = tuple(value[order] for value in values)
    refit, point = continuation._point(*canonical, budget=240)
    assert point is not None
    random = np.random.default_rng(legacy._bootstrap_seed(DIGEST))
    draws = [legacy._stratified_patient_bootstrap_indices(canonical[3], random) for _ in range(128)]
    calls = 0

    def controlled_point(*arrays: np.ndarray, budget: int) -> tuple[Any, Any]:
        nonlocal calls
        assert budget == ITERATIONS
        if calls == 0:
            expected = canonical
        else:
            expected = tuple(value[draws[calls - 1]] for value in canonical)
        assert all(
            np.array_equal(left, right) for left, right in zip(arrays, expected, strict=True)
        )
        calls += 1
        return refit, point if calls == 1 or calls - 1 <= successful else None

    monkeypatch.setattr(continuation, "_point", controlled_point)
    result = continuation.fit_continuation_gene(*values, request_digest=DIGEST)
    assert calls == REPLICATES + 1
    assert result.bootstrap_requested == result.bootstrap_attempted == REPLICATES
    assert result.bootstrap_successful == successful
    assert result.accepted is (successful == REQUIRED)
    if successful == REQUIRED - 1:
        assert result.summary is None
        assert "103 of 128" in str(result.failure_reason)
    else:
        assert result.summary is not None
        assert result.summary.bootstrap.replicates_successful == REQUIRED
        assert result.summary.bootstrap.full_model_r2.replicates == REQUIRED


def test_continuation_point_fit_never_calls_the_legacy_cross_fit_or_solver(
    monkeypatch: pytest.MonkeyPatch,
    paired_oracle: tuple[Any, ...],
) -> None:
    values, _old, _thirty, accepted = paired_oracle
    assert accepted.summary is not None

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("the continuation must not call the legacy point-fitting path")

    monkeypatch.setattr(legacy, "_cross_fit", forbidden)
    monkeypatch.setattr(legacy, "fit_huber", forbidden)
    monkeypatch.setattr(
        continuation,
        "_bootstrap",
        lambda *_args, **_kwargs: (
            accepted.bootstrap_successful,
            accepted.summary.bootstrap,
        ),
    )
    result = continuation.fit_continuation_gene(*values, request_digest=DIGEST)
    assert result.accepted
    assert result.summary == accepted.summary


def test_heavy_tailed_seed_nine_recovers_failed_bootstrap_draws_without_relabeling_baseline() -> (
    None
):
    random = np.random.default_rng(9)
    x = random.normal(size=(96, 2))
    x[:, 1] = 0.95 * x[:, 0] + 0.1 * x[:, 1]
    protein = 1.2 * x[:, 0] - 0.4 * x[:, 1] + random.standard_t(1.5, size=96) * 0.3
    protein[:38] += random.normal(loc=1.0, scale=3.0, size=38)
    folds = (np.arange(96) % 5).astype(np.int8)
    digest = "sha256:" + "9" * 64
    first = continuation._fit_continuation_gene_for_budget(
        x[:, 1],
        x[:, 0],
        protein,
        folds,
        request_digest=digest,
        budget=30,
    )
    recovered = continuation.fit_continuation_gene(
        x[:, 1],
        x[:, 0],
        protein,
        folds,
        request_digest=digest,
    )
    assert first.accepted
    assert recovered.accepted
    assert first.bootstrap_successful == LEGACY_SLOW_SUCCESSES
    assert recovered.bootstrap_successful == REPLICATES
    assert first.comparison_bootstrap_seed == recovered.comparison_bootstrap_seed
    assert first.budget == LEGACY_ITERATIONS
    assert recovered.budget == ITERATIONS


@pytest.mark.parametrize("budget", [0, 30, 60, 120, 239, 241])
def test_public_profile_rejects_all_other_integer_budgets(budget: int) -> None:
    with pytest.raises(ValueError, match="requires budget=240"):
        continuation.fit_continuation_gene(*_gene(), request_digest=DIGEST, budget=budget)


@pytest.mark.parametrize("budget", [True, False, 240.0, "240", None, np.int64(240)])
def test_public_budget_does_not_coerce_noninteger_values(budget: Any) -> None:
    with pytest.raises(TypeError, match="exact integer"):
        continuation.fit_continuation_gene(*_gene(), request_digest=DIGEST, budget=budget)


def test_invalid_digest_and_infinite_measurements_are_rejected() -> None:
    with pytest.raises(ValueError, match="canonical lowercase sha256"):
        continuation.fit_continuation_gene(*_gene(), request_digest="unbound")
    cnv, rna, protein, folds = _gene()
    cnv[0] = np.inf
    with pytest.raises(ValueError, match="infinity"):
        continuation.fit_continuation_gene(cnv, rna, protein, folds, request_digest=DIGEST)
