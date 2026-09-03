"""Scientific and replay tests for the research-only GLIO-ECGI engine."""

from __future__ import annotations

import json

import numpy as np
import pytest

from glio_proteogen.research.proteogenomic_state import (
    MAX_JSON_SAFE_INTEGER,
    EdgeKind,
    EvidenceModality,
    EvidenceObservation,
    EvidenceState,
    ExternalKinaseEstimate,
    ExternalKinaseProfile,
    GraphEdge,
    GraphNode,
    InferenceSupport,
    NodeKind,
    ProteogenomicStateRequest,
    ReplayVerificationRequest,
    StateClassification,
    algorithm_profile,
    analyze_proteogenomic_state,
    canonical_request_digest,
    demo_topology_provenance_digest,
    synthetic_demo_request,
    verify_proteogenomic_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)
from glio_proteogen.research.proteogenomic_state.canonical import sha256_digest


def _digest(label: str) -> str:
    return sha256_digest({"test-source": label})


def _observation(  # noqa: PLR0913
    observation_id: str,
    node_id: str,
    effect: float | None,
    *,
    state: EvidenceState = EvidenceState.OBSERVED,
    modality: EvidenceModality = EvidenceModality.PROTEOMICS,
    error: float | None = 1.0,
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
        provenance_digest=_digest(observation_id),
    )


def _two_node_request() -> ProteogenomicStateRequest:
    return ProteogenomicStateRequest(
        sample_id="sample.oracle",
        nodes=(
            GraphNode(node_id="protein.source", kind=NodeKind.PROTEIN),
            GraphNode(node_id="protein.target", kind=NodeKind.PROTEIN),
        ),
        edges=(
            GraphEdge(
                edge_id="edge.regulation",
                source_id="protein.source",
                target_id="protein.target",
                kind=EdgeKind.REGULATES,
                sign=1,
                weight=1.0,
            ),
        ),
        observations=(_observation("obs.source", "protein.source", 0.2),),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )


def test_small_graph_matches_direct_quadratic_reference_solver() -> None:
    request = _two_node_request()
    result = analyze_proteogenomic_state(request)
    ridge = algorithm_profile().constants.ridge_penalty
    edge_weight = next(
        item.weight
        for item in algorithm_profile().relation_weights
        if item.kind is EdgeKind.REGULATES
    )
    matrix = np.asarray([[ridge + 1.0, 0.0], [-edge_weight, ridge + edge_weight]])
    expected = np.linalg.solve(matrix, np.asarray([0.2, 0.0]))
    by_id = {item.node_id: item for item in result.node_states}
    assert by_id["protein.source"].activity == pytest.approx(expected[0], abs=2e-6)
    assert by_id["protein.target"].activity == pytest.approx(expected[1], abs=2e-6)
    trace = result.solver.first_pass.objective_trace
    assert result.solver.first_pass.objective_trace_semantics == (
        "paired_frozen_parent_baseline_candidate"
    )
    assert all(
        candidate <= baseline + 1e-8
        for baseline, candidate in zip(trace[::2], trace[1::2], strict=True)
    )


def test_robust_one_node_solution_matches_independent_bisection_oracle() -> None:
    observations = (
        _observation("obs.high", "protein.signal", 5.0, error=0.2, quality=1.0),
        _observation("obs.low", "protein.signal", -1.0, error=0.8, quality=0.45),
    )
    request = ProteogenomicStateRequest(
        sample_id="sample.robust-oracle",
        nodes=(GraphNode(node_id="protein.signal", kind=NodeKind.PROTEIN),),
        observations=observations,
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    constants = algorithm_profile().constants

    def derivative(value: float) -> float:
        total = constants.ridge_penalty * value
        for item in observations:
            assert item.standardized_effect is not None and item.standard_error is not None
            residual = (value - item.standardized_effect) / item.standard_error
            clipped = max(-constants.huber_delta, min(constants.huber_delta, residual))
            total += item.quality_weight * clipped / item.standard_error
        return total

    lower, upper = -20.0, 20.0
    for _ in range(160):
        midpoint = (lower + upper) / 2.0
        if derivative(midpoint) < 0.0:
            lower = midpoint
        else:
            upper = midpoint
    expected = (lower + upper) / 2.0
    state = analyze_proteogenomic_state(request).node_states[0]
    assert state.activity == pytest.approx(expected, abs=2e-6)


def test_input_order_does_not_change_request_or_result_digest() -> None:
    first = _two_node_request()
    reordered = first.model_copy(
        update={
            "nodes": tuple(reversed(first.nodes)),
            "edges": tuple(reversed(first.edges)),
            "observations": tuple(reversed(first.observations)),
        }
    )
    first_result = analyze_proteogenomic_state(first)
    reordered_result = analyze_proteogenomic_state(reordered)
    assert canonical_request_digest(first) == canonical_request_digest(reordered)
    assert first_result == reordered_result


def test_replay_recomputes_every_digest_and_solver_trace() -> None:
    request = _two_node_request()
    result = analyze_proteogenomic_state(request)
    verified = verify_proteogenomic_replay(
        ReplayVerificationRequest(request=request, result=result)
    )
    assert verified.verified is True
    assert verified.request_digest_match is True
    assert verified.profile_digest_match is True
    assert verified.solver_trace_match is True
    assert verified.result_digest_match is True
    assert verified.semantic_match is True

    forged = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    forged_request = ReplayVerificationRequest.model_construct(request=request, result=forged)
    rejected = verify_proteogenomic_replay(forged_request)
    assert rejected.verified is False
    assert rejected.result_digest_match is False
    assert "no result claims" in rejected.message


def test_browser_number_round_trip_preserves_replay_receipt() -> None:
    request = _two_node_request()
    result = analyze_proteogenomic_state(request)
    envelope = json.dumps(
        {
            "request": request.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    browser_document = json.loads(envelope, parse_int=lambda value: int(float(value)))
    browser_envelope = ReplayVerificationRequest.model_validate_json(
        json.dumps(browser_document, separators=(",", ":")), strict=True
    )

    assert algorithm_profile().constants.random_seed_modulus == MAX_JSON_SAFE_INTEGER + 1
    assert result.provenance.deterministic_seed <= MAX_JSON_SAFE_INTEGER
    assert (
        browser_envelope.result.provenance.deterministic_seed
        == result.provenance.deterministic_seed
    )
    assert verify_proteogenomic_replay(browser_envelope).verified is True


def test_left_censoring_is_one_sided_and_missingness_never_becomes_negative() -> None:
    request = ProteogenomicStateRequest(
        sample_id="sample.censoring",
        nodes=(
            GraphNode(node_id="protein.censored", kind=NodeKind.PROTEIN),
            GraphNode(node_id="protein.censored.nonbinding", kind=NodeKind.PROTEIN),
            GraphNode(node_id="protein.censored.near-zero", kind=NodeKind.PROTEIN),
            GraphNode(node_id="protein.missing", kind=NodeKind.PROTEIN),
            GraphNode(node_id="protein.unsupported", kind=NodeKind.PROTEIN),
        ),
        observations=(
            _observation(
                "obs.censored",
                "protein.censored",
                -1.0,
                state=EvidenceState.LEFT_CENSORED,
                error=0.1,
            ),
            _observation(
                "obs.censored.nonbinding",
                "protein.censored.nonbinding",
                1.0,
                state=EvidenceState.LEFT_CENSORED,
                error=0.1,
            ),
            _observation(
                "obs.censored.near-zero",
                "protein.censored.near-zero",
                -0.1,
                state=EvidenceState.LEFT_CENSORED,
                error=0.1,
            ),
            _observation(
                "obs.missing",
                "protein.missing",
                None,
                state=EvidenceState.MISSING,
                error=None,
                quality=0.0,
            ),
            _observation(
                "obs.unsupported",
                "protein.unsupported",
                None,
                state=EvidenceState.UNSUPPORTED,
                error=None,
                quality=0.0,
            ),
        ),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    result = analyze_proteogenomic_state(request)
    states = {item.node_id: item for item in result.node_states}
    assert states["protein.censored"].activity is not None
    assert states["protein.censored"].activity < -0.8
    assert states["protein.censored"].classification is StateClassification.SUPPRESSED
    assert states["protein.censored"].censored_count == 1
    for node_id in ("protein.censored.nonbinding", "protein.censored.near-zero"):
        assert states[node_id].support is InferenceSupport.ABSTAINED
        assert states[node_id].classification is StateClassification.NOT_ESTIMABLE
        assert states[node_id].activity is None
        assert states[node_id].evidence_count == 1
        assert states[node_id].censored_count == 1
    for node_id in ("protein.missing", "protein.unsupported"):
        assert states[node_id].support is InferenceSupport.ABSTAINED
        assert states[node_id].classification is StateClassification.NOT_ESTIMABLE
        assert states[node_id].activity is None


def test_essential_complex_subunit_caps_the_complex_state() -> None:
    request = ProteogenomicStateRequest(
        sample_id="sample.complex",
        nodes=(
            GraphNode(node_id="protein.essential", kind=NodeKind.PROTEIN),
            GraphNode(node_id="protein.abundant", kind=NodeKind.PROTEIN),
            GraphNode(node_id="complex.machine", kind=NodeKind.COMPLEX),
        ),
        edges=(
            GraphEdge(
                edge_id="edge.essential",
                source_id="protein.essential",
                target_id="complex.machine",
                kind=EdgeKind.MEMBER_OF,
                sign=1,
                weight=2.0,
                essential=True,
            ),
            GraphEdge(
                edge_id="edge.abundant",
                source_id="protein.abundant",
                target_id="complex.machine",
                kind=EdgeKind.MEMBER_OF,
                sign=1,
                weight=1.0,
            ),
        ),
        observations=(
            _observation("obs.essential", "protein.essential", -0.9, error=0.2),
            _observation("obs.abundant", "protein.abundant", 1.8, error=0.2),
        ),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    result = analyze_proteogenomic_state(request)
    states = {item.node_id: item for item in result.node_states}
    complex_activity = states["complex.machine"].activity
    abundant_activity = states["protein.abundant"].activity
    assert complex_activity is not None and abundant_activity is not None
    assert complex_activity < abundant_activity
    assert any(
        item.kind.value == "edge_family" and item.omitted == "member_of"
        for item in states["complex.machine"].ablation_effects
    )


def _kinase_request() -> ProteogenomicStateRequest:
    kinase_nodes = (
        GraphNode(node_id="kinase.primary", kind=NodeKind.KINASE),
        GraphNode(node_id="kinase.sparse", kind=NodeKind.KINASE),
    )
    sites = tuple(
        GraphNode(node_id=f"phosphosite.s{index}", kind=NodeKind.PHOSPHOSITE)
        for index in range(1, 9)
    )
    primary_edges = tuple(
        GraphEdge(
            edge_id=f"edge.primary.{index}",
            source_id="kinase.primary",
            target_id=f"phosphosite.s{index}",
            kind=EdgeKind.KINASE_SUBSTRATE,
            sign=1,
            weight=1.0,
        )
        for index in range(1, 4)
    )
    sparse_edges = tuple(
        GraphEdge(
            edge_id=f"edge.sparse.{index}",
            source_id="kinase.sparse",
            target_id=f"phosphosite.s{index}",
            kind=EdgeKind.KINASE_SUBSTRATE,
            sign=1,
            weight=1.0,
        )
        for index in range(1, 3)
    )
    observations = tuple(
        _observation(
            f"obs.site.{index}",
            f"phosphosite.s{index}",
            effect,
            modality=EvidenceModality.PHOSPHOPROTEOMICS,
            error=0.15,
        )
        for index, effect in enumerate((2.0, 1.8, 1.6, 0.1, -0.2, -0.6, -1.7, -1.9), start=1)
    )
    return ProteogenomicStateRequest(
        sample_id="sample.kinase",
        nodes=kinase_nodes + sites,
        edges=primary_edges + sparse_edges,
        observations=observations,
        bootstrap_replicates=8,
        permutation_replicates=256,
        external_kinase_profile=ExternalKinaseProfile(
            profile_id="kinophos.test",
            source_digest=_digest("external-kinase"),
            estimates=(
                ExternalKinaseEstimate(
                    kinase_id="kinase.primary",
                    activity=1.0,
                    lower_bound=0.5,
                    upper_bound=1.5,
                ),
            ),
        ),
    )


def test_kinase_rank_enrichment_bh_feedback_and_sparse_abstention() -> None:
    result = analyze_proteogenomic_state(_kinase_request())
    kinases = {item.node_id: item for item in result.kinase_states}
    primary = kinases["kinase.primary"]
    sparse = kinases["kinase.sparse"]
    assert primary.mapped_substrates == 3
    assert primary.enrichment_score is not None and primary.enrichment_score > 0.0
    assert primary.p_value is not None
    assert primary.q_value is not None
    assert primary.activity is not None and primary.activity > 0.0
    assert sparse.mapped_substrates == 2
    assert sparse.support is InferenceSupport.ABSTAINED
    assert sparse.q_value is None
    assert result.external_kinase_comparison is not None
    assert result.external_kinase_comparison.matches[0].kinase_id == "kinase.primary"
    assert result.external_kinase_comparison.unmatched_local_ids == ("kinase.sparse",)
    assert result.external_kinase_comparison.external_ids_with_abstained_local_estimates == ()
    assert "never merged" in result.external_kinase_comparison.note


def test_contradictory_external_profile_is_comparison_only() -> None:
    request = _kinase_request()
    without_external = request.model_copy(update={"external_kinase_profile": None})
    contradictory = request.model_copy(
        update={
            "external_kinase_profile": ExternalKinaseProfile(
                profile_id="kinophos.contradictory",
                source_digest=_digest("contradictory-external"),
                estimates=(
                    ExternalKinaseEstimate(
                        kinase_id="kinase.primary",
                        activity=-3.0,
                        lower_bound=-3.5,
                        upper_bound=-2.5,
                    ),
                ),
            )
        }
    )
    baseline_result = analyze_proteogenomic_state(without_external)
    contradictory_result = analyze_proteogenomic_state(contradictory)
    assert contradictory_result.solver == baseline_result.solver
    assert contradictory_result.node_states == baseline_result.node_states
    assert contradictory_result.kinase_states == baseline_result.kinase_states
    assert (
        contradictory_result.provenance.computational_digest
        == baseline_result.provenance.computational_digest
    )
    assert contradictory_result.request_digest != baseline_result.request_digest
    assert contradictory_result.external_kinase_comparison is not None
    match = contradictory_result.external_kinase_comparison.matches[0]
    assert match.direction_agreement is False
    assert match.interval_overlap is False


def test_demo_is_versioned_bounded_synthetic_and_json_round_trips() -> None:
    request = synthetic_demo_request()
    profile = algorithm_profile()
    assert request.sample_id == "synthetic-glioma-demo-v1"
    assert len(request.nodes) == 64
    assert len(request.edges) == 83
    assert profile.profile_id == request.profile_id
    assert profile.claim_ceiling == "limited_unvalidated_caller_graph"
    assert profile.demo_graph_digest.startswith("sha256:")
    assert request.topology_provenance is not None
    assert request.topology_provenance.topology_digest == profile.demo_graph_digest
    assert request.topology_provenance.derivation == "synthetic_abstraction"
    assert len(request.topology_provenance.sources) == 3
    assert {source.record_id for source in request.topology_provenance.sources} == {
        "R-HSA-177929",
        "R-HSA-1257604",
        "R-HSA-69278",
    }
    assert all(
        source.resource_name == "Reactome"
        and source.resource_release == "97"
        and source.role == "biological_context"
        for source in request.topology_provenance.sources
    )
    assert profile.demo_topology_provenance_digest == demo_topology_provenance_digest()
    assert (
        sha256_digest(profile.model_dump(mode="json", exclude={"profile_digest"}))
        == profile.profile_digest
    )
    assert profile.constants.relaxed_max_iterations == 96
    assert (
        profile.constants.ablation_permutation_policy == "common_base_computational_request_domain"
    )
    assert (
        profile.constants.left_censor_support_policy
        == "binding_upper_bound_or_independent_directed_evidence"
    )
    assert profile.constants.interval_lower_quantile == 0.05
    assert profile.constants.interval_upper_quantile == 0.95
    round_tripped = ProteogenomicStateRequest.model_validate_json(request.model_dump_json())
    assert round_tripped == request
    assert "synthetic" in json.loads(request.model_dump_json())["sample_id"]


def test_demo_result_surfaces_exact_request_topology_provenance() -> None:
    request = synthetic_demo_request().model_copy(
        update={"bootstrap_replicates": 8, "permutation_replicates": 32}
    )
    result = analyze_proteogenomic_state(request)
    assert result.provenance.topology == request.topology_provenance
    assert result.provenance.topology is not None
    assert result.provenance.topology.topology_digest == algorithm_profile().demo_graph_digest


@pytest.mark.parametrize("derivation", ["caller_curated", "synthetic_abstraction"])
def test_unvalidated_caller_graph_estimates_never_exceed_limited_support(
    derivation: str,
) -> None:
    request = synthetic_demo_request()
    assert request.topology_provenance is not None
    topology = request.topology_provenance.model_copy(update={"derivation": derivation})
    bounded = request.model_copy(
        update={
            "bootstrap_replicates": 8,
            "permutation_replicates": 32,
            "topology_provenance": topology,
        }
    )

    result = analyze_proteogenomic_state(bounded)
    estimated = tuple(
        state
        for state in (*result.node_states, *result.kinase_states)
        if state.support is not InferenceSupport.ABSTAINED
    )

    assert estimated
    assert all(state.support is InferenceSupport.LIMITED for state in estimated)
    assert any(state.q_value is not None for state in result.kinase_states)
    assert any("LIMITED" in limitation for limitation in result.limitations)


def test_cooperative_cancellation_preserves_uninterrupted_receipt() -> None:
    request = synthetic_demo_request().model_copy(
        update={"bootstrap_replicates": 8, "permutation_replicates": 32}
    )
    baseline = analyze_proteogenomic_state(request)
    controlled = analyze_proteogenomic_state(request, cancellation=CancellationContext())
    cancelled = CancellationContext()
    cancelled.cancel()

    assert controlled == baseline
    with pytest.raises(InferenceCancelledError, match="cancelled"):
        analyze_proteogenomic_state(request, cancellation=cancelled)
