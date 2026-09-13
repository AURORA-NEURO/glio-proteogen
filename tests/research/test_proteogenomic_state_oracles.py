"""Locked numerical oracles for the experimental GLIO-ECGI algorithm."""

from __future__ import annotations

import numpy as np
import pytest

from glio_proteogen.research.proteogenomic_state import (
    EdgeKind,
    EvidenceModality,
    EvidenceObservation,
    EvidenceState,
    GraphEdge,
    GraphNode,
    InferenceConvergenceError,
    InferenceSupport,
    NodeKind,
    ProteogenomicStateRequest,
    algorithm_profile,
    analyze_proteogenomic_state,
    computational_request_digest,
    synthetic_demo_request,
)
from glio_proteogen.research.proteogenomic_state import engine as engine_module
from glio_proteogen.research.proteogenomic_state.canonical import sha256_digest


def _observation(
    observation_id: str,
    node_id: str,
    effect: float,
    *,
    modality: EvidenceModality = EvidenceModality.PROTEOMICS,
    error: float = 0.2,
) -> EvidenceObservation:
    return EvidenceObservation(
        observation_id=observation_id,
        node_id=node_id,
        modality=modality,
        state=EvidenceState.OBSERVED,
        standardized_effect=effect,
        standard_error=error,
        quality_weight=1.0,
        provenance_digest=sha256_digest({"oracle": observation_id}),
    )


def test_locked_signed_cycle_recovers_at_least_ninety_percent_of_directions() -> None:
    node_count = 20
    nodes = tuple(
        GraphNode(node_id=f"protein.n{index}", kind=NodeKind.PROTEIN) for index in range(node_count)
    )
    edges = tuple(
        GraphEdge(
            edge_id=f"edge.cycle.{index}",
            source_id=f"protein.n{index}",
            target_id=f"protein.n{(index + 1) % node_count}",
            kind=EdgeKind.REGULATES,
            sign=-1,
            weight=2.0,
        )
        for index in range(node_count)
    )
    truth = tuple(1.0 if index % 2 == 0 else -1.0 for index in range(node_count))
    observations = tuple(
        _observation(f"obs.anchor.{index}", f"protein.n{index}", truth[index], error=0.1)
        for index in range(0, node_count, 4)
    )
    result = analyze_proteogenomic_state(
        ProteogenomicStateRequest(
            sample_id="oracle.direction.cycle",
            nodes=nodes,
            edges=edges,
            observations=observations,
            bootstrap_replicates=32,
            permutation_replicates=32,
        )
    )
    inferred = {item.node_id: item.activity for item in result.node_states}
    recovered = sum(
        inferred[f"protein.n{index}"] is not None
        and float(inferred[f"protein.n{index}"]) * truth[index] > 0.0
        for index in range(node_count)
    )
    assert recovered / node_count >= 0.90


def test_nominal_ninety_percent_intervals_have_locked_simulation_coverage() -> None:
    rng = np.random.default_rng(20260827)
    truth = 0.8
    standard_error = 0.4
    covered = 0
    # Two hundred locked simulations keep Monte Carlo error in the oracle itself
    # materially below the acceptance band's five-percentage-point half-width.
    simulations = 200
    for index, measured in enumerate(rng.normal(truth, standard_error, simulations)):
        request = ProteogenomicStateRequest(
            sample_id=f"oracle.coverage.{index}",
            nodes=(GraphNode(node_id="protein.signal", kind=NodeKind.PROTEIN),),
            observations=(
                _observation(
                    "obs.signal",
                    "protein.signal",
                    float(measured),
                    error=standard_error,
                ),
            ),
            bootstrap_replicates=64,
            permutation_replicates=32,
        )
        state = analyze_proteogenomic_state(request).node_states[0]
        assert state.lower_bound is not None and state.upper_bound is not None
        covered += state.lower_bound <= truth <= state.upper_bound
    coverage = covered / simulations
    assert covered == 176
    assert 0.85 <= coverage <= 0.95


def test_independent_benjamini_hochberg_calculation_matches_demo_q_values() -> None:
    kinases = analyze_proteogenomic_state(synthetic_demo_request()).kinase_states
    tested = [item for item in kinases if item.p_value is not None]
    ordered = sorted(enumerate(tested), key=lambda item: (float(item[1].p_value), item[1].node_id))
    expected = [1.0] * len(tested)
    running = 1.0
    for reverse_rank, (original_index, item) in enumerate(reversed(ordered), start=1):
        rank = len(tested) - reverse_rank + 1
        assert item.p_value is not None
        running = min(running, item.p_value * len(tested) / rank)
        expected[original_index] = min(1.0, running)
    for item, expected_q in zip(tested, expected, strict=True):
        assert item.q_value == pytest.approx(expected_q, abs=2e-8)
    significant = [
        item
        for item in tested
        if item.q_value is not None
        and item.q_value <= algorithm_profile().constants.kinase_q_threshold
    ]
    assert significant
    assert all(item.support is InferenceSupport.LIMITED for item in significant)


def test_reliability_weighted_rank_statistic_matches_hand_calculation() -> None:
    sites = tuple(
        GraphNode(node_id=f"phosphosite.s{index}", kind=NodeKind.PHOSPHOSITE)
        for index in range(1, 7)
    )
    request = ProteogenomicStateRequest(
        sample_id="oracle.rank",
        nodes=(GraphNode(node_id="kinase.k", kind=NodeKind.KINASE), *sites),
        edges=tuple(
            GraphEdge(
                edge_id=f"edge.substrate.{index}",
                source_id="kinase.k",
                target_id=f"phosphosite.s{index}",
                kind=EdgeKind.KINASE_SUBSTRATE,
                sign=1,
                weight=1.0,
            )
            for index in range(4, 7)
        ),
        observations=tuple(
            _observation(
                f"obs.site.{index}",
                f"phosphosite.s{index}",
                float(index),
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
                error=0.2,
            )
            for index in range(1, 7)
        ),
        bootstrap_replicates=8,
        permutation_replicates=256,
    )
    kinase = analyze_proteogenomic_state(request).kinase_states[0]
    # Six ordered sites have normalized ranks 0,.2,.4,.6,.8,1.  The three
    # substrates therefore have centered ranks .2,.6,1 and equal reliability.
    expected_rank_statistic = (0.2 + 0.6 + 1.0) / 3.0
    assert kinase.rank_statistic == pytest.approx(expected_rank_statistic, abs=1e-8)


def test_all_null_kinase_screen_controls_empirical_discovery_fraction() -> None:
    rng = np.random.default_rng(20260827)
    kinase_count = 24
    site_count = kinase_count * 3
    simulations = 500
    kinases = tuple(
        GraphNode(node_id=f"kinase.k{index}", kind=NodeKind.KINASE) for index in range(kinase_count)
    )
    sites = tuple(
        GraphNode(node_id=f"phosphosite.s{index}", kind=NodeKind.PHOSPHOSITE)
        for index in range(site_count)
    )
    edges = tuple(
        GraphEdge(
            edge_id=f"edge.null.{kinase}.{offset}",
            source_id=f"kinase.k{kinase}",
            target_id=f"phosphosite.s{3 * kinase + offset}",
            kind=EdgeKind.KINASE_SUBSTRATE,
            sign=1,
            weight=1.0,
        )
        for kinase in range(kinase_count)
        for offset in range(3)
    )
    threshold = algorithm_profile().constants.kinase_q_threshold
    false_discovery_proportions: list[float] = []
    for simulation in range(simulations):
        observations = tuple(
            EvidenceObservation(
                observation_id=f"obs.null.{index}",
                node_id=f"phosphosite.s{index}",
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
                state=EvidenceState.OBSERVED,
                standardized_effect=float(effect),
                standard_error=0.5,
                quality_weight=1.0,
                provenance_digest=sha256_digest({"oracle": simulation, "observation": index}),
            )
            for index, effect in enumerate(rng.normal(0.0, 1.0, site_count))
        )
        request = ProteogenomicStateRequest(
            sample_id=f"oracle.kinase.null.{simulation}",
            nodes=kinases + sites,
            edges=edges,
            observations=observations,
            bootstrap_replicates=8,
            permutation_replicates=256,
        )
        graph = engine_module._prepare(request)
        first_pass = engine_module._solve_checked(
            graph,
            stage=f"oracle:null:{simulation}",
            excluded_edge_kinds=frozenset({EdgeKind.KINASE_SUBSTRATE}),
        )
        estimates = engine_module._kinase_enrichment(
            computational_request_digest(request),
            graph,
            first_pass.values,
            request.permutation_replicates,
        )
        discoveries = sum(
            item.q_value is not None and item.q_value <= threshold for item in estimates
        )
        # Every hypothesis is null, so the realized FDP is one when the run
        # makes any discovery and zero otherwise.  Its simulation mean is FDR.
        false_discovery_proportions.append(float(discoveries > 0))
    empirical_fdr = float(np.mean(false_discovery_proportions))
    assert empirical_fdr == pytest.approx(0.086, abs=1e-12)
    assert empirical_fdr == pytest.approx(threshold, abs=0.02)


def test_extreme_conflict_is_finite_and_nonconvergence_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = ProteogenomicStateRequest(
        sample_id="oracle.extreme",
        nodes=(GraphNode(node_id="protein.signal", kind=NodeKind.PROTEIN),),
        observations=(
            _observation("obs.high", "protein.signal", 20.0, error=0.01),
            _observation("obs.low", "protein.signal", -20.0, error=0.01),
        ),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    baseline = analyze_proteogenomic_state(request)
    assert baseline.node_states[0].activity is not None
    assert np.isfinite(baseline.node_states[0].activity)
    monkeypatch.setattr(
        engine_module,
        "CONSTANTS",
        engine_module.CONSTANTS.model_copy(update={"max_iterations": 1, "tolerance": 1e-15}),
    )
    with pytest.raises(InferenceConvergenceError, match="analysis:evidence_graph"):
        analyze_proteogenomic_state(
            request.model_copy(update={"observations": (request.observations[0],)})
        )
