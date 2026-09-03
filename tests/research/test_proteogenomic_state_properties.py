"""Property and causal-stage tests for directed GLIO-ECGI inference."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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
    ReplayVerificationRequest,
    StateClassification,
    analyze_proteogenomic_state,
    computational_request_digest,
    graph_topology_digest,
    synthetic_demo_request,
    verify_proteogenomic_replay,
)
from glio_proteogen.research.proteogenomic_state import engine as engine_module
from glio_proteogen.research.proteogenomic_state.canonical import sha256_digest


def _observation(  # noqa: PLR0913
    observation_id: str,
    node_id: str,
    effect: float | None,
    *,
    state: EvidenceState = EvidenceState.OBSERVED,
    modality: EvidenceModality = EvidenceModality.PROTEOMICS,
    error: float | None = 0.25,
    quality: float = 1.0,
) -> EvidenceObservation:
    return EvidenceObservation(
        observation_id=observation_id,
        node_id=node_id,
        modality=modality,
        state=state,
        standardized_effect=effect,
        standard_error=error,
        quality_weight=quality,
        provenance_digest=sha256_digest({"property-observation": observation_id}),
    )


def _directed_pair_request(
    *,
    observed_node: str,
    effect: float,
    sign: int,
) -> ProteogenomicStateRequest:
    return ProteogenomicStateRequest(
        sample_id="property.directed-pair",
        nodes=(
            GraphNode(node_id="protein.source", kind=NodeKind.PROTEIN),
            GraphNode(node_id="protein.target", kind=NodeKind.PROTEIN),
        ),
        edges=(
            GraphEdge(
                edge_id="edge.source-to-target",
                source_id="protein.source",
                target_id="protein.target",
                kind=EdgeKind.REGULATES,
                sign=sign,
                weight=1.5,
            ),
        ),
        observations=(_observation("obs.signal", observed_node, effect),),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )


@given(
    effect=st.floats(
        min_value=0.1,
        max_value=4.0,
        allow_nan=False,
        allow_infinity=False,
        width=64,
    ),
    sign=st.sampled_from((-1, 1)),
)
@settings(max_examples=12, deadline=None)
def test_directed_evidence_never_flows_upstream_and_does_flow_forward(
    effect: float,
    sign: int,
) -> None:
    downstream_only = analyze_proteogenomic_state(
        _directed_pair_request(
            observed_node="protein.target",
            effect=effect,
            sign=sign,
        )
    )
    downstream_by_id = {item.node_id: item for item in downstream_only.node_states}
    assert downstream_by_id["protein.source"].support is InferenceSupport.ABSTAINED
    assert downstream_by_id["protein.source"].activity is None

    upstream = analyze_proteogenomic_state(
        _directed_pair_request(
            observed_node="protein.source",
            effect=effect,
            sign=sign,
        )
    )
    upstream_by_id = {item.node_id: item for item in upstream.node_states}
    source = upstream_by_id["protein.source"].activity
    target = upstream_by_id["protein.target"].activity
    assert source is not None and target is not None
    assert source * target * sign > 0.0


@given(
    first_effect=st.floats(
        min_value=-4.0,
        max_value=4.0,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
    second_effect=st.floats(
        min_value=-4.0,
        max_value=4.0,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
    sign=st.sampled_from((-1, 1)),
)
@settings(max_examples=12, deadline=None)
def test_graph_collection_order_is_a_semantic_property(
    first_effect: float,
    second_effect: float,
    sign: int,
) -> None:
    request = ProteogenomicStateRequest(
        sample_id="property.order",
        nodes=tuple(
            GraphNode(node_id=f"protein.n{index}", kind=NodeKind.PROTEIN) for index in range(3)
        ),
        edges=(
            GraphEdge(
                edge_id="edge.0",
                source_id="protein.n0",
                target_id="protein.n1",
                kind=EdgeKind.REGULATES,
                sign=sign,
                weight=0.8,
            ),
            GraphEdge(
                edge_id="edge.1",
                source_id="protein.n1",
                target_id="protein.n2",
                kind=EdgeKind.REGULATES,
                sign=1,
                weight=1.2,
            ),
        ),
        observations=(
            _observation("obs.0", "protein.n0", first_effect),
            _observation("obs.1", "protein.n1", second_effect),
        ),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    reordered = request.model_copy(
        update={
            "nodes": tuple(reversed(request.nodes)),
            "edges": tuple(reversed(request.edges)),
            "observations": tuple(reversed(request.observations)),
        }
    )
    assert analyze_proteogenomic_state(request) == analyze_proteogenomic_state(reordered)


@given(state=st.sampled_from((EvidenceState.MISSING, EvidenceState.UNSUPPORTED)))
@settings(max_examples=4, deadline=None)
def test_inactive_evidence_cannot_change_numerical_inference(state: EvidenceState) -> None:
    base = _directed_pair_request(observed_node="protein.source", effect=1.25, sign=1)
    inactive = _observation(
        f"obs.{state.value}",
        "protein.target",
        None,
        state=state,
        error=None,
        quality=0.0,
    )
    augmented = base.model_copy(update={"observations": (*base.observations, inactive)})
    base_result = analyze_proteogenomic_state(base)
    augmented_result = analyze_proteogenomic_state(augmented)
    assert augmented_result.solver == base_result.solver
    assert augmented_result.node_states == base_result.node_states
    assert augmented_result.kinase_states == base_result.kinase_states
    assert augmented_result.request_digest != base_result.request_digest


def test_metadata_only_changes_cannot_reseed_or_change_demo_inference() -> None:
    request = synthetic_demo_request()
    baseline = analyze_proteogenomic_state(request)
    topology = request.topology_provenance
    assert topology is not None

    renamed_nodes = (
        request.nodes[0].model_copy(update={"display_name": "Renamed display-only node"}),
        *request.nodes[1:],
    )
    renamed_topology_digest = graph_topology_digest(
        {"nodes": renamed_nodes, "edges": request.edges}
    )
    display_variant = request.model_copy(
        update={
            "nodes": renamed_nodes,
            "topology_provenance": topology.model_copy(
                update={"topology_digest": renamed_topology_digest}
            ),
        }
    )

    changed_observation = request.observations[0].model_copy(
        update={"provenance_digest": sha256_digest({"metadata-only": "changed"})}
    )
    observation_variant = request.model_copy(
        update={"observations": (changed_observation, *request.observations[1:])}
    )

    changed_source = topology.sources[0].model_copy(
        update={
            "record_title": "Metadata-only topology title",
            "source_digest": sha256_digest({"metadata-only": "topology-source"}),
        }
    )
    topology_variant = request.model_copy(
        update={
            "topology_provenance": topology.model_copy(
                update={
                    "curation_note": "Metadata-only curation note.",
                    "sources": (changed_source, *topology.sources[1:]),
                }
            )
        }
    )
    variants = (
        request.model_copy(update={"sample_id": "same-biology-renamed"}),
        display_variant,
        observation_variant,
        topology_variant,
        request.model_copy(update={"topology_provenance": None}),
    )

    for variant in variants:
        result = analyze_proteogenomic_state(variant)
        assert result.provenance.computational_digest == baseline.provenance.computational_digest
        assert result.provenance.deterministic_seed == baseline.provenance.deterministic_seed
        assert result.solver == baseline.solver
        assert result.node_states == baseline.node_states
        assert result.kinase_states == baseline.kinase_states
        assert result.request_digest != baseline.request_digest
        assert result.result_digest != baseline.result_digest
        verification = verify_proteogenomic_replay(
            ReplayVerificationRequest(request=variant, result=result)
        )
        assert verification.verified is True


def test_computational_digest_binds_every_computational_field_family() -> None:
    document = _directed_pair_request(
        observed_node="protein.source", effect=1.25, sign=1
    ).model_dump(mode="json")
    baseline = computational_request_digest(document)
    mutations: tuple[tuple[tuple[str | int, ...], Any], ...] = (
        (("profile_id",), "glio-ecgi/changed"),
        (("bootstrap_replicates",), 9),
        (("permutation_replicates",), 33),
        (("nodes", 0, "node_id"), "protein.renamed"),
        (("nodes", 0, "kind"), "proteoform"),
        (("edges", 0, "edge_id"), "edge.renamed"),
        (("edges", 0, "source_id"), "protein.target"),
        (("edges", 0, "target_id"), "protein.source"),
        (("edges", 0, "kind"), "member_of"),
        (("edges", 0, "sign"), -1),
        (("edges", 0, "weight"), 1.6),
        (("edges", 0, "essential"), True),
        (("observations", 0, "observation_id"), "obs.renamed"),
        (("observations", 0, "node_id"), "protein.target"),
        (("observations", 0, "modality"), "phosphoproteomics"),
        (("observations", 0, "state"), "left_censored"),
        (("observations", 0, "standardized_effect"), 1.5),
        (("observations", 0, "standard_error"), 0.5),
        (("observations", 0, "quality_weight"), 0.5),
    )
    for path, replacement in mutations:
        candidate = deepcopy(document)
        target: Any = candidate
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = replacement
        assert computational_request_digest(candidate) != baseline


def test_antithetic_bootstrap_perturbations_are_balanced_and_replayable() -> None:
    request = _directed_pair_request(observed_node="protein.source", effect=1.0, sign=1)
    second_observation = _observation(
        "obs.second",
        "protein.target",
        -0.5,
        error=0.6,
    )
    graph = engine_module._prepare(
        request.model_copy(update={"observations": (*request.observations, second_observation)})
    )

    even = engine_module._antithetic_perturbations(np.random.default_rng(17), graph.observations, 8)
    replay = engine_module._antithetic_perturbations(
        np.random.default_rng(17), graph.observations, 8
    )
    odd = engine_module._antithetic_perturbations(np.random.default_rng(17), graph.observations, 9)
    odd_replay = engine_module._antithetic_perturbations(
        np.random.default_rng(17), graph.observations, 9
    )

    assert even.shape == (8, 2)
    assert odd.shape == (9, 2)
    np.testing.assert_array_equal(even, replay)
    np.testing.assert_array_equal(odd, odd_replay)
    np.testing.assert_allclose(even[:4] + even[4:], 0.0, atol=0.0)
    assert np.any(odd[0] != 0.0)
    np.testing.assert_allclose(odd[1:5] + odd[5:], 0.0, atol=0.0)


@given(
    lower=st.floats(
        min_value=-0.25,
        max_value=0.25,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
    upper=st.floats(
        min_value=-0.25,
        max_value=0.25,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
)
def test_interval_classification_is_neutral_only_inside_closed_thresholds(
    lower: float,
    upper: float,
) -> None:
    ordered_lower, ordered_upper = sorted((lower, upper))
    assert (
        engine_module._classification(ordered_lower, ordered_upper) is StateClassification.NEUTRAL
    )


def _supported_kinase_request() -> ProteogenomicStateRequest:
    sites = tuple(
        GraphNode(node_id=f"phosphosite.s{index}", kind=NodeKind.PHOSPHOSITE)
        for index in range(1, 9)
    )
    return ProteogenomicStateRequest(
        sample_id="property.kinase-stage",
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
            for index in range(1, 4)
        ),
        observations=tuple(
            _observation(
                f"obs.site.{index}",
                f"phosphosite.s{index}",
                effect,
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
                error=0.15,
            )
            for index, effect in enumerate((2.0, 1.8, 1.6, 0.1, -0.2, -0.6, -1.7, -1.9), start=1)
        ),
        bootstrap_replicates=8,
        permutation_replicates=256,
    )


def test_kinase_substrate_edges_are_isolated_until_supported_feedback_pass() -> None:
    request = _supported_kinase_request()
    graph = engine_module._prepare(request)
    digest = computational_request_digest(request)
    pipeline = engine_module._run_pipeline(
        digest,
        graph,
        request.permutation_replicates,
        stage="test:kinase-isolation",
    )
    contaminated = engine_module._solve_checked(graph, stage="test:contaminated")
    kinase_index = graph.node_index["kinase.k"]
    site_index = graph.node_index["phosphosite.s1"]
    assert pipeline.first_pass.values[kinase_index] == pytest.approx(0.0, abs=1e-12)
    assert pipeline.first_pass.values[site_index] > contaminated.values[site_index]
    assert pipeline.feedback
    assert pipeline.second_pass.values[kinase_index] > 0.0
    assert pipeline.second_pass.values[site_index] != pytest.approx(
        pipeline.first_pass.values[site_index], abs=1e-8
    )


def test_abstained_kinase_edges_cannot_shrink_phosphosites_toward_zero() -> None:
    sites = tuple(
        GraphNode(node_id=f"phosphosite.s{index}", kind=NodeKind.PHOSPHOSITE)
        for index in range(1, 5)
    )
    request = ProteogenomicStateRequest(
        sample_id="property.abstained-kinase-is-inert",
        nodes=(GraphNode(node_id="kinase.sparse", kind=NodeKind.KINASE), *sites),
        edges=tuple(
            GraphEdge(
                edge_id=f"edge.sparse.{index}",
                source_id="kinase.sparse",
                target_id=f"phosphosite.s{index}",
                kind=EdgeKind.KINASE_SUBSTRATE,
                sign=1,
                weight=2.0,
            )
            for index in range(1, 3)
        ),
        observations=tuple(
            _observation(
                f"obs.sparse-site.{index}",
                f"phosphosite.s{index}",
                effect,
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
                error=0.2,
            )
            for index, effect in enumerate((1.8, 1.4, -0.7, 0.5), start=1)
        ),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    graph = engine_module._prepare(request)
    pipeline = engine_module._run_pipeline(
        computational_request_digest(request),
        graph,
        request.permutation_replicates,
        stage="test:abstained-kinase-is-inert",
    )
    edge_free_request = request.model_copy(update={"edges": ()})
    edge_free_graph = engine_module._prepare(edge_free_request)
    edge_free_pipeline = engine_module._run_pipeline(
        computational_request_digest(edge_free_request),
        edge_free_graph,
        edge_free_request.permutation_replicates,
        stage="test:edge-free-control",
    )

    assert pipeline.feedback == ()
    np.testing.assert_allclose(
        pipeline.second_pass.values,
        edge_free_pipeline.second_pass.values,
        rtol=0.0,
        atol=1e-12,
    )

    result = analyze_proteogenomic_state(request)
    kinase = result.kinase_states[0]
    site = next(item for item in result.node_states if item.node_id == "phosphosite.s1")
    assert kinase.support is InferenceSupport.ABSTAINED
    assert kinase.mapped_substrates == 2
    assert all(driver.driver_id != "edge.sparse.1" for driver in site.top_drivers)
    kinase_ablation = next(
        effect
        for effect in site.ablation_effects
        if effect.kind.value == "edge_family" and effect.omitted == "kinase_substrate"
    )
    assert kinase_ablation.activity_delta == 0.0


def test_pathway_evidence_is_inferred_only_in_the_declared_direction() -> None:
    nodes = (
        GraphNode(node_id="protein.driver", kind=NodeKind.PROTEIN),
        GraphNode(node_id="pathway.output", kind=NodeKind.PATHWAY),
    )
    edge = GraphEdge(
        edge_id="edge.pathway",
        source_id="protein.driver",
        target_id="pathway.output",
        kind=EdgeKind.PARTICIPATES_IN,
        sign=1,
        weight=1.5,
    )
    downstream_only = ProteogenomicStateRequest(
        sample_id="property.pathway.downstream",
        nodes=nodes,
        edges=(edge,),
        observations=(_observation("obs.pathway", "pathway.output", 2.0),),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    downstream_states = {
        item.node_id: item for item in analyze_proteogenomic_state(downstream_only).node_states
    }
    assert downstream_states["protein.driver"].support is InferenceSupport.ABSTAINED
    assert downstream_states["protein.driver"].activity is None

    upstream_only = downstream_only.model_copy(
        update={
            "sample_id": "property.pathway.upstream",
            "observations": (_observation("obs.protein", "protein.driver", 2.0),),
        }
    )
    upstream_states = {
        item.node_id: item for item in analyze_proteogenomic_state(upstream_only).node_states
    }
    assert upstream_states["pathway.output"].activity is not None
    assert upstream_states["pathway.output"].activity > 0.0


def test_every_ablation_recomputes_kinase_selection_and_both_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _supported_kinase_request()
    original = engine_module._kinase_enrichment
    calls: list[tuple[str, EvidenceModality | None, EdgeKind | None]] = []

    def recording_enrichment(  # noqa: PLR0913
        request_digest: str,
        graph: engine_module._PreparedGraph,
        values: np.ndarray[tuple[int], np.dtype[np.float64]],
        permutations: int,
        *,
        excluded_modality: EvidenceModality | None = None,
        excluded_edge_kind: EdgeKind | None = None,
        cancellation: engine_module.CancellationContext | None = None,
    ) -> tuple[engine_module._KinaseEstimate, ...]:
        calls.append((request_digest, excluded_modality, excluded_edge_kind))
        return original(
            request_digest,
            graph,
            values,
            permutations,
            excluded_modality=excluded_modality,
            excluded_edge_kind=excluded_edge_kind,
            cancellation=cancellation,
        )

    monkeypatch.setattr(engine_module, "_kinase_enrichment", recording_enrichment)
    analyze_proteogenomic_state(request)
    digest = computational_request_digest(request)
    assert calls == [
        (digest, None, None),
        (digest, EvidenceModality.PHOSPHOPROTEOMICS, None),
        (digest, None, EdgeKind.KINASE_SUBSTRATE),
    ]


def test_disconnected_edge_ablation_uses_common_null_draws_and_has_zero_effect() -> None:
    base = _supported_kinase_request()
    request = base.model_copy(
        update={
            "nodes": (
                *base.nodes,
                GraphNode(node_id="protein.disconnected.source", kind=NodeKind.PROTEIN),
                GraphNode(node_id="protein.disconnected.target", kind=NodeKind.PROTEIN),
            ),
            "edges": (
                *base.edges,
                GraphEdge(
                    edge_id="edge.disconnected",
                    source_id="protein.disconnected.source",
                    target_id="protein.disconnected.target",
                    kind=EdgeKind.REGULATES,
                    sign=1,
                    weight=1.0,
                ),
            ),
        }
    )
    graph = engine_module._prepare(request)
    digest = computational_request_digest(request)
    complete = engine_module._run_pipeline(
        digest,
        graph,
        request.permutation_replicates,
        stage="test:common-random:complete",
    )
    ablated = engine_module._run_pipeline(
        digest,
        graph,
        request.permutation_replicates,
        stage="test:common-random:ablated",
        excluded_edge_kind=EdgeKind.REGULATES,
    )
    assert complete.kinase_estimates == ablated.kinase_estimates
    assert complete.feedback == ablated.feedback
    np.testing.assert_array_equal(complete.second_pass.values, ablated.second_pass.values)

    result = analyze_proteogenomic_state(request)
    estimated_states = tuple(
        state
        for state in (*result.node_states, *result.kinase_states)
        if state.ablation_effects
    )
    assert estimated_states
    for state in estimated_states:
        effect = next(
            item
            for item in state.ablation_effects
            if item.kind.value == "edge_family" and item.omitted == "regulates"
        )
        assert effect.activity_delta == 0.0


def test_relaxed_secondary_solve_retries_strictly_and_never_uses_partial_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _directed_pair_request(observed_node="protein.source", effect=1.0, sign=1)
    graph = engine_module._prepare(request)
    original = engine_module._solve
    calls: list[bool] = []

    def fail_relaxed(*args: object, **kwargs: object) -> engine_module._SolveOutcome:
        relaxed = bool(kwargs.get("relaxed", False))
        calls.append(relaxed)
        outcome = original(*args, **kwargs)
        return replace(outcome, converged=False) if relaxed else outcome

    monkeypatch.setattr(engine_module, "_solve", fail_relaxed)
    recovered = engine_module._solve_checked(
        graph,
        stage="test:retry",
        relaxed_first=True,
    )
    assert recovered.converged is True
    assert calls == [True, False]

    def never_converges(*args: object, **kwargs: object) -> engine_module._SolveOutcome:
        return replace(original(*args, **kwargs), converged=False)

    monkeypatch.setattr(engine_module, "_solve", never_converges)
    with pytest.raises(InferenceConvergenceError, match="test:hard-failure"):
        engine_module._solve_checked(
            graph,
            stage="test:hard-failure",
            relaxed_first=True,
        )


def test_bootstrap_feedback_fails_closed_if_supported_mapping_becomes_incoherent() -> None:
    supported = engine_module._KinaseEstimate(
        kinase_id="kinase.k",
        node_index=0,
        mapped_substrates=3,
        rank_statistic=0.5,
        enrichment_score=1.0,
        p_value=0.01,
        q_value=0.01,
        null_standard_deviation=0.5,
    )
    no_sites = ProteogenomicStateRequest(
        sample_id="property.bootstrap.no-sites",
        nodes=(GraphNode(node_id="kinase.k", kind=NodeKind.KINASE),),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    no_site_graph = engine_module._prepare(no_sites)
    assert (
        engine_module._bootstrap_feedback(
            no_site_graph, np.zeros(1, dtype=np.float64), (supported,)
        )
        == ()
    )

    sites_without_edges = ProteogenomicStateRequest(
        sample_id="property.bootstrap.no-mapping",
        nodes=(
            GraphNode(node_id="kinase.k", kind=NodeKind.KINASE),
            *(
                GraphNode(node_id=f"phosphosite.s{index}", kind=NodeKind.PHOSPHOSITE)
                for index in range(3)
            ),
        ),
        observations=tuple(
            _observation(
                f"obs.s{index}",
                f"phosphosite.s{index}",
                float(index),
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
            )
            for index in range(3)
        ),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    no_mapping_graph = engine_module._prepare(sites_without_edges)
    with pytest.raises(ValueError, match="lost its mapped substrates"):
        engine_module._bootstrap_feedback(
            no_mapping_graph,
            np.zeros(len(no_mapping_graph.node_ids), dtype=np.float64),
            (supported,),
        )
