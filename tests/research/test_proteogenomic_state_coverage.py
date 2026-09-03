"""Exhaustive branch tests for ECGI contracts and numerical safety fallbacks."""

from __future__ import annotations

import json
from copy import deepcopy

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.research.proteogenomic_state import (
    EdgeKind,
    EvidenceModality,
    EvidenceObservation,
    EvidenceState,
    ExternalKinaseEstimate,
    ExternalKinaseProfile,
    GraphEdge,
    GraphNode,
    InferenceSupport,
    KinaseInference,
    NodeInference,
    NodeKind,
    ProteogenomicStateRequest,
    ProteogenomicStateResult,
    ReplayVerificationRequest,
    StateClassification,
    UnverifiedProteogenomicStateResult,
    analyze_proteogenomic_state,
    synthetic_demo_request,
    verify_proteogenomic_replay,
)
from glio_proteogen.research.proteogenomic_state import canonical as canonical_module
from glio_proteogen.research.proteogenomic_state import engine as engine_module
from glio_proteogen.research.proteogenomic_state import profile as profile_module
from glio_proteogen.research.proteogenomic_state.canonical import (
    result_payload_digest,
    sha256_digest,
)

SOURCE = sha256_digest("coverage-source")


def test_profile_rejects_an_unpinned_numpy_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profile_module.np, "__version__", "2.5.1")
    with pytest.raises(RuntimeError, match="profile-pinned NumPy"):
        profile_module.algorithm_profile()


def _observation(  # noqa: PLR0913
    observation_id: str,
    node_id: str,
    effect: float | None = 0.5,
    *,
    state: EvidenceState = EvidenceState.OBSERVED,
    error: float | None = 0.2,
    quality: float = 1.0,
    modality: EvidenceModality = EvidenceModality.PROTEOMICS,
) -> EvidenceObservation:
    return EvidenceObservation(
        observation_id=observation_id,
        node_id=node_id,
        modality=modality,
        state=state,
        standardized_effect=effect,
        standard_error=error,
        quality_weight=quality,
        provenance_digest=SOURCE,
    )


def _minimal_request() -> ProteogenomicStateRequest:
    return ProteogenomicStateRequest(
        sample_id="coverage.minimal",
        nodes=(GraphNode(node_id="protein.a", kind=NodeKind.PROTEIN),),
        observations=(_observation("obs.a", "protein.a"),),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )


def _estimated_node(**updates: object) -> NodeInference:
    values: dict[str, object] = {
        "node_id": "protein.a",
        "kind": NodeKind.PROTEIN,
        "activity": 0.0,
        "lower_bound": -0.1,
        "upper_bound": 0.1,
        "classification": StateClassification.NEUTRAL,
        "support": InferenceSupport.SUPPORTED,
        "evidence_count": 1,
        "observed_count": 1,
        "censored_count": 0,
        "stability": 1.0,
        "discordance": 0.0,
    }
    values.update(updates)
    return NodeInference(**values)  # type: ignore[arg-type]


def _estimated_kinase(node_id: str, activity: float) -> KinaseInference:
    lower = activity - 0.1
    upper = activity + 0.1
    classification = (
        StateClassification.ACTIVATED
        if lower > 0.25
        else StateClassification.SUPPRESSED
        if upper < -0.25
        else StateClassification.NEUTRAL
    )
    return KinaseInference(
        node_id=node_id,
        activity=activity,
        lower_bound=lower,
        upper_bound=upper,
        classification=classification,
        support=InferenceSupport.SUPPORTED,
        evidence_count=0,
        observed_count=0,
        censored_count=0,
        stability=1.0,
        discordance=0.0,
        mapped_substrates=3,
        rank_statistic=0.2,
        enrichment_score=0.5,
        null_standard_deviation=0.4,
        p_value=0.05,
        q_value=0.05,
    )


def test_canonical_dict_projection_and_request_property() -> None:
    request = _minimal_request()
    dumped = request.model_dump(mode="json")
    assert canonical_module.normalized_request(dumped) == canonical_module.normalized_request(
        request
    )
    assert request.request_digest == canonical_module.canonical_request_digest(dumped)


def test_canonical_dict_projection_does_not_mutate_nested_caller_data() -> None:
    document = synthetic_demo_request().model_dump(mode="json")
    external = document["external_kinase_profile"]
    topology = document["topology_provenance"]
    assert external is not None
    assert topology is not None
    external["estimates"].reverse()
    topology["sources"].reverse()
    original = deepcopy(document)

    normalized = canonical_module.normalized_request(document)

    assert document == original
    assert normalized is not document
    assert normalized["external_kinase_profile"] is not external
    normalized_estimates = normalized["external_kinase_profile"]["estimates"]
    assert [item["kinase_id"] for item in normalized_estimates] == sorted(
        item["kinase_id"] for item in external["estimates"]
    )
    assert normalized["topology_provenance"] is not topology
    normalized_sources = normalized["topology_provenance"]["sources"]
    assert [item["source_id"] for item in normalized_sources] == sorted(
        item["source_id"] for item in topology["sources"]
    )


def test_remaining_observation_and_external_contract_rejections() -> None:
    with pytest.raises(ValidationError, match="positive quality"):
        _observation("obs.zero", "protein.a", quality=0.0)
    with pytest.raises(ValidationError, match="must contain"):
        ExternalKinaseEstimate(
            kinase_id="kinase.k",
            activity=1.0,
            lower_bound=-1.0,
            upper_bound=0.0,
        )
    estimate = ExternalKinaseEstimate(
        kinase_id="kinase.k", activity=0.0, lower_bound=-1.0, upper_bound=1.0
    )
    with pytest.raises(ValidationError, match="must be unique"):
        ExternalKinaseProfile(
            profile_id="external.duplicate",
            source_digest=SOURCE,
            estimates=(estimate, estimate),
        )


def test_remaining_graph_identity_and_reference_rejections() -> None:
    nodes = (
        GraphNode(node_id="protein.a", kind=NodeKind.PROTEIN),
        GraphNode(node_id="protein.b", kind=NodeKind.PROTEIN),
    )
    edge = GraphEdge(
        edge_id="edge.a",
        source_id="protein.a",
        target_id="protein.b",
        kind=EdgeKind.REGULATES,
        sign=1,
        weight=1.0,
    )
    with pytest.raises(ValidationError, match="edge identifiers"):
        ProteogenomicStateRequest(
            sample_id="coverage.edges",
            nodes=nodes,
            edges=(edge, edge),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )
    observation = _observation("obs.a", "protein.a")
    with pytest.raises(ValidationError, match="observation identifiers"):
        ProteogenomicStateRequest(
            sample_id="coverage.observations",
            nodes=nodes,
            observations=(observation, observation),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )
    with pytest.raises(ValidationError, match="kinase count"):
        ProteogenomicStateRequest(
            sample_id="coverage.kinases",
            nodes=tuple(
                GraphNode(node_id=f"kinase.k{index}", kind=NodeKind.KINASE) for index in range(129)
            ),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )
    with pytest.raises(ValidationError, match="observation references"):
        ProteogenomicStateRequest(
            sample_id="coverage.unresolved.observation",
            nodes=(nodes[0],),
            observations=(_observation("obs.missing", "protein.absent"),),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )


@pytest.mark.parametrize(
    ("source", "target", "kind", "message"),
    [
        (NodeKind.PROTEIN, NodeKind.PROTEIN, EdgeKind.PROTEOFORM_OF, "proteoform_of"),
        (NodeKind.PROTEIN, NodeKind.PROTEIN, EdgeKind.SITE_OF, "site_of"),
    ],
)
def test_remaining_edge_type_rejections(
    source: NodeKind, target: NodeKind, kind: EdgeKind, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        ProteogenomicStateRequest(
            sample_id="coverage.edge.kind",
            nodes=(
                GraphNode(node_id="protein.source", kind=source),
                GraphNode(node_id="protein.target", kind=target),
            ),
            edges=(
                GraphEdge(
                    edge_id="edge.invalid",
                    source_id="protein.source",
                    target_id="protein.target",
                    kind=kind,
                    sign=1,
                    weight=1.0,
                ),
            ),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {
                "support": InferenceSupport.ABSTAINED,
                "classification": StateClassification.NOT_ESTIMABLE,
                "abstention_reason": "absent",
            },
            "cannot carry estimates",
        ),
        (
            {
                "support": InferenceSupport.ABSTAINED,
                "activity": None,
                "lower_bound": None,
                "upper_bound": None,
                "abstention_reason": "absent",
            },
            "must be not_estimable",
        ),
        (
            {
                "support": InferenceSupport.ABSTAINED,
                "activity": None,
                "lower_bound": None,
                "upper_bound": None,
                "classification": StateClassification.NOT_ESTIMABLE,
            },
            "require a reason",
        ),
        ({"activity": None}, "require activity and interval"),
        ({"activity": 2.0}, "interval must contain"),
        ({"classification": StateClassification.NOT_ESTIMABLE}, "cannot be not_estimable"),
        ({"abstention_reason": "unexpected"}, "cannot carry an abstention"),
    ],
)
def test_node_inference_rejects_incoherent_states(updates: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _estimated_node(**updates)


def test_kinase_enrichment_fields_match_mapping_support() -> None:
    base = _estimated_kinase("kinase.k", 0.5).model_dump()
    with pytest.raises(ValidationError, match="fewer than three"):
        KinaseInference(**{**base, "mapped_substrates": 2})
    for field in (
        "rank_statistic",
        "enrichment_score",
        "null_standard_deviation",
        "p_value",
        "q_value",
    ):
        incomplete = {**base, field: None}
        with pytest.raises(ValidationError, match="requires score"):
            KinaseInference(**incomplete)


def test_result_receipt_rejects_each_tampering_dimension() -> None:
    result = analyze_proteogenomic_state(_minimal_request())
    wrong = "sha256:" + "f" * 64
    bad_request_provenance = result.model_copy(
        update={"provenance": result.provenance.model_copy(update={"request_digest": wrong})}
    )
    with pytest.raises(ValueError, match="provenance request"):
        bad_request_provenance.receipt_is_content_bound()
    bad_profile_provenance = result.model_copy(
        update={"provenance": result.provenance.model_copy(update={"profile_digest": wrong})}
    )
    with pytest.raises(ValueError, match="provenance profile"):
        bad_profile_provenance.receipt_is_content_bound()
    duplicate = result.model_copy(update={"node_states": result.node_states * 2})
    with pytest.raises(ValueError, match="must be unique"):
        duplicate.receipt_is_content_bound()
    forged = result.model_copy(update={"result_digest": wrong})
    with pytest.raises(ValueError, match="canonical result"):
        forged.receipt_is_content_bound()
    assert result_payload_digest(result) == result.result_digest


def test_authoritative_result_rejects_supported_claim_but_replay_can_audit_it() -> None:
    request = _minimal_request()
    result = analyze_proteogenomic_state(request)
    payload = result.model_dump(mode="json")
    payload["node_states"][0]["support"] = InferenceSupport.SUPPORTED.value
    payload["result_digest"] = result_payload_digest(payload)
    encoded = json.dumps(payload, separators=(",", ":"))

    with pytest.raises(ValidationError, match="cannot claim supported inference"):
        ProteogenomicStateResult.model_validate_json(encoded, strict=True)

    unverified = UnverifiedProteogenomicStateResult.model_validate_json(encoded, strict=True)
    replay = verify_proteogenomic_replay(
        ReplayVerificationRequest(request=request, result=unverified)
    )
    assert replay.verified is False
    assert replay.semantic_match is False


def test_rank_ties_singletons_small_strata_and_empty_bh_path() -> None:
    assert engine_module._rank_values(np.asarray([1.0])).tolist() == [0.5]
    assert engine_module._rank_values(np.asarray([1.0, 1.0, 2.0])).tolist() == [0.25, 0.25, 1.0]
    assert engine_module._strata(np.asarray([1.0, 2.0, 3.0])).tolist() == [0, 0, 0]
    request = ProteogenomicStateRequest(
        sample_id="coverage.empty.bh",
        nodes=(GraphNode(node_id="phosphosite.a", kind=NodeKind.PHOSPHOSITE),),
        observations=(
            _observation(
                "obs.site",
                "phosphosite.a",
                modality=EvidenceModality.PHOSPHOPROTEOMICS,
            ),
        ),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    assert analyze_proteogenomic_state(request).kinase_states == ()


def test_solver_backtracking_acceptance_and_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = engine_module._prepare(_minimal_request())
    monkeypatch.setattr(
        engine_module,
        "CONSTANTS",
        engine_module.CONSTANTS.model_copy(update={"max_iterations": 1, "tolerance": 1e-15}),
    )
    calls = 0

    def accept_second(*_args: object) -> float:
        nonlocal calls
        calls += 1
        return 0.0 if calls in {1, 4} else 1.0

    monkeypatch.setattr(engine_module, "_objective", accept_second)
    engine_module._solve(graph)
    assert calls == 4

    calls = 0

    def never_accept(*_args: object) -> float:
        nonlocal calls
        calls += 1
        return 0.0 if calls == 1 else 1.0

    monkeypatch.setattr(engine_module, "_objective", never_accept)
    engine_module._solve(graph)
    assert calls == 20


def test_zero_residual_discordance_and_inactive_censor_driver() -> None:
    empty = ProteogenomicStateRequest(
        sample_id="coverage.empty",
        nodes=(GraphNode(node_id="protein.a", kind=NodeKind.PROTEIN),),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    graph = engine_module._prepare(empty)
    values = np.asarray([0.0])
    assert engine_module._discordance(0, values, graph) == 0.0
    censored = empty.model_copy(
        update={
            "observations": (
                _observation(
                    "obs.censored",
                    "protein.a",
                    1.0,
                    state=EvidenceState.LEFT_CENSORED,
                ),
            )
        }
    )
    censored_graph = engine_module._prepare(censored)
    drivers = engine_module._drivers(0, values, censored_graph, ())
    assert drivers[0].signed_contribution == 0.0


def test_external_comparison_skips_abstentions_and_handles_tied_ranks() -> None:
    nodes = (
        GraphNode(node_id="kinase.a", kind=NodeKind.KINASE),
        GraphNode(node_id="kinase.b", kind=NodeKind.KINASE),
        GraphNode(node_id="kinase.c", kind=NodeKind.KINASE),
    )
    profile = ExternalKinaseProfile(
        profile_id="external.coverage",
        source_digest=SOURCE,
        estimates=tuple(
            ExternalKinaseEstimate(
                kinase_id=node.node_id,
                activity=float(index),
                lower_bound=float(index) - 0.1,
                upper_bound=float(index) + 0.1,
            )
            for index, node in enumerate(nodes)
        ),
    )
    request = ProteogenomicStateRequest(
        sample_id="coverage.external",
        nodes=nodes,
        external_kinase_profile=profile,
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    abstained = KinaseInference(
        node_id="kinase.c",
        classification=StateClassification.NOT_ESTIMABLE,
        support=InferenceSupport.ABSTAINED,
        evidence_count=0,
        observed_count=0,
        censored_count=0,
        abstention_reason="insufficient substrates",
        mapped_substrates=0,
    )
    comparison = engine_module._external_comparison(
        request,
        (
            _estimated_kinase("kinase.a", 0.5),
            _estimated_kinase("kinase.b", 0.5),
            abstained,
        ),
    )
    assert comparison is not None
    assert len(comparison.matches) == 2
    assert comparison.unmatched_local_ids == ("kinase.c",)
    assert comparison.external_ids_with_abstained_local_estimates == ("kinase.c",)
    assert comparison.rank_correlation is None

    ranked = engine_module._external_comparison(
        request,
        (
            _estimated_kinase("kinase.a", 0.5),
            _estimated_kinase("kinase.b", 1.5),
            abstained,
        ),
    )
    assert ranked is not None
    assert ranked.rank_correlation == 1.0

    partial_external = request.model_copy(
        update={
            "external_kinase_profile": profile.model_copy(
                update={"estimates": profile.estimates[:2]}
            )
        }
    )
    unmatched = engine_module._external_comparison(
        partial_external,
        (
            _estimated_kinase("kinase.a", 0.5),
            _estimated_kinase("kinase.b", 1.5),
            abstained,
        ),
    )
    assert unmatched is not None
    assert unmatched.unmatched_local_ids == ("kinase.c",)
    assert unmatched.external_ids_with_abstained_local_estimates == ()


def test_incomplete_internal_kinase_estimate_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nodes = (
        GraphNode(node_id="kinase.k", kind=NodeKind.KINASE),
        *(
            GraphNode(node_id=f"phosphosite.s{index}", kind=NodeKind.PHOSPHOSITE)
            for index in range(3)
        ),
    )
    edges = tuple(
        GraphEdge(
            edge_id=f"edge.s{index}",
            source_id="kinase.k",
            target_id=f"phosphosite.s{index}",
            kind=EdgeKind.KINASE_SUBSTRATE,
            sign=1,
            weight=1.0,
        )
        for index in range(3)
    )
    observations = tuple(
        _observation(
            f"obs.s{index}",
            f"phosphosite.s{index}",
            modality=EvidenceModality.PHOSPHOPROTEOMICS,
        )
        for index in range(3)
    )
    request = ProteogenomicStateRequest(
        sample_id="coverage.incomplete.kinase",
        nodes=nodes,
        edges=edges,
        observations=observations,
        bootstrap_replicates=8,
        permutation_replicates=32,
    )

    def incomplete(
        _digest: str,
        graph: engine_module._PreparedGraph,
        _values: np.ndarray[tuple[int], np.dtype[np.float64]],
        _permutations: int,
        **_kwargs: object,
    ) -> tuple[engine_module._KinaseEstimate, ...]:
        return (
            engine_module._KinaseEstimate(
                "kinase.k", graph.node_index["kinase.k"], 3, None, None, None, None, None
            ),
        )

    monkeypatch.setattr(engine_module, "_kinase_enrichment", incomplete)
    with pytest.raises(ValueError, match="incomplete"):
        analyze_proteogenomic_state(request)
