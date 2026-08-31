from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from glio_proteogen.research.kncc_gbm_factor_graph import (
    DEMO_ID,
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    PROFILE_ID,
    RELATIONSHIP,
    FactorGraphNodeKind,
    KnccGbmFactorGraphReplayVerificationResult,
    KnccGbmFactorGraphRequest,
    KnccGbmFactorGraphResult,
    UnverifiedKnccGbmFactorGraphResult,
    algorithm_profile,
    analyze_kncc_gbm_factor_graph,
    demo_request_digest,
    demo_semantic_oracle_digest,
    factor_graph_topology,
    synthetic_demo_request,
)
from glio_proteogen.research.kncc_gbm_factor_graph import profile as factor_profile_module
from glio_proteogen.research.kncc_gbm_factor_graph.canonical import (
    canonical_request_digest,
    profile_payload_digest,
    result_payload_digest,
    sha256_digest,
    topology_payload_digest,
)
from glio_proteogen.research.kncc_gbm_factor_graph.contracts import (
    FactorGraphTopology,
)
from glio_proteogen.research.kncc_gbm_factor_graph.errors import (
    KnccGbmFactorGraphProfileIntegrityError,
)
from glio_proteogen.research.kncc_gbm_factor_graph.profile import (
    composition_semantic_digest,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.catalog import (
    load_kinase_transition_catalog,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.contracts import (
    LongitudinalGbmKinaseTransitionRequest,
    UnverifiedLongitudinalGbmKinaseTransitionResult,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.catalog import (
    EXPECTED_PATHWAYS,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    LongitudinalGbmReactomeTransitionRequest,
    UnverifiedLongitudinalGbmReactomeTransitionResult,
)

ZERO_DIGEST = "sha256:" + "0" * 64
ONE_DIGEST = "sha256:" + "1" * 64


@pytest.fixture(scope="module")
def demo_receipt() -> tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult]:
    request = synthetic_demo_request()
    return request, analyze_kncc_gbm_factor_graph(request)


def _minimal_six_point_reactome_request() -> LongitudinalGbmReactomeTransitionRequest:
    source = synthetic_demo_request().reactome_request
    template = source.time_points[0]
    observation = template.observations[0]
    points = tuple(
        template.model_copy(
            update={
                "time_point_id": f"reactome.limit.tp{i}",
                "time_offset_days": float(i),
                "observations": (
                    observation.model_copy(update={"observation_id": f"reactome.limit.obs{i}"}),
                ),
            }
        )
        for i in range(6)
    )
    return LongitudinalGbmReactomeTransitionRequest(
        series_id="reactome.limit.series",
        assay_compatibility=source.assay_compatibility,
        normalization_reference=source.normalization_reference,
        time_points=points,
        bootstrap_replicates=source.bootstrap_replicates,
    )


def _minimal_six_point_kinase_request() -> LongitudinalGbmKinaseTransitionRequest:
    source = synthetic_demo_request().kinase_request
    template = source.time_points[0]
    observation = template.observations[0]
    points = tuple(
        template.model_copy(
            update={
                "time_point_id": f"kinase.limit.tp{i}",
                "time_offset_days": float(i),
                "observations": (
                    observation.model_copy(update={"observation_id": f"kinase.limit.obs{i}"}),
                ),
            }
        )
        for i in range(6)
    )
    return LongitudinalGbmKinaseTransitionRequest(
        series_id="kinase.limit.series",
        assay_compatibility=source.assay_compatibility,
        normalization_reference=source.normalization_reference,
        time_points=points,
        bootstrap_replicates=source.bootstrap_replicates,
    )


def test_request_locks_relationship_identity_limits_and_child_types() -> None:
    request = synthetic_demo_request()
    assert request.profile_id == PROFILE_ID
    assert request.analysis_id == DEMO_ID
    assert request.relationship == RELATIONSHIP
    assert len(request.reactome_request.time_points) == 4
    assert len(request.kinase_request.time_points) == 4
    assert MAX_REQUEST_BYTES == 4_194_304
    assert MAX_RESULT_BYTES == 8_388_608
    assert MAX_REPLAY_BYTES == 16_777_216

    payload = request.model_dump(mode="json")
    payload["relationship"] = "numerical_cross_modal_fusion"
    with pytest.raises(ValidationError):
        KnccGbmFactorGraphRequest.model_validate(payload)


@pytest.mark.parametrize("child", ["reactome", "kinase"])
def test_request_enforces_five_time_point_outer_limit(child: str) -> None:
    request = synthetic_demo_request()
    payload: dict[str, object] = {
        "analysis_id": "limit.test",
        "reactome_request": request.reactome_request,
        "kinase_request": request.kinase_request,
    }
    if child == "reactome":
        payload["reactome_request"] = _minimal_six_point_reactome_request()
    else:
        payload["kinase_request"] = _minimal_six_point_kinase_request()
    with pytest.raises(ValidationError, match="limited to five time points"):
        KnccGbmFactorGraphRequest(**payload)


def test_outer_request_digest_delegates_modality_specific_set_normalization() -> None:
    request = synthetic_demo_request()
    reactome = request.reactome_request
    kinase = request.kinase_request
    reactome_first = reactome.time_points[0].model_copy(
        update={"observations": tuple(reversed(reactome.time_points[0].observations))}
    )
    kinase_first = kinase.time_points[0].model_copy(
        update={"observations": tuple(reversed(kinase.time_points[0].observations))}
    )
    reordered = KnccGbmFactorGraphRequest(
        analysis_id=request.analysis_id,
        reactome_request=reactome.model_copy(
            update={"time_points": (reactome_first, *reactome.time_points[1:])}
        ),
        kinase_request=kinase.model_copy(
            update={"time_points": (kinase_first, *kinase.time_points[1:])}
        ),
    )
    assert canonical_request_digest(reordered) == canonical_request_digest(request)


def test_topology_is_the_locked_two_block_annotation_inventory() -> None:
    topology = factor_graph_topology()
    assert len(topology.nodes) == 41
    assert len(topology.containment_edges) == 39
    assert topology.cross_block_edges == ()
    assert topology.numerical_cross_block_edge_count == 0
    assert topology.topology_digest == topology_payload_digest(topology)
    assert topology.topology_digest == (
        "sha256:d9baef8ce0b125a26f547edd0441e05c772249fcef3ab57b95d0eea0c777f9c7"
    )
    assert all(edge.computational_role == "annotation_only" for edge in topology.containment_edges)
    assert all(edge.numerical_weight is None for edge in topology.containment_edges)

    by_kind = {
        kind: tuple(node for node in topology.nodes if node.kind is kind)
        for kind in FactorGraphNodeKind
    }
    assert len(by_kind[FactorGraphNodeKind.COMPUTATION_BLOCK]) == 2
    assert len(by_kind[FactorGraphNodeKind.GLOBAL_RECURRENCE_FACTOR]) == 1
    assert len(by_kind[FactorGraphNodeKind.REACTOME_PATHWAY_FACTOR]) == 10
    assert len(by_kind[FactorGraphNodeKind.KINASE_SIGNATURE_FACTOR]) == 24
    assert len(by_kind[FactorGraphNodeKind.SUBTYPE_SIGNATURE_FACTOR]) == 4
    assert tuple(
        node.biological_identifier for node in by_kind[FactorGraphNodeKind.REACTOME_PATHWAY_FACTOR]
    ) == tuple(item[1] for item in EXPECTED_PATHWAYS)
    assert tuple(
        node.biological_identifier for node in by_kind[FactorGraphNodeKind.KINASE_SIGNATURE_FACTOR]
    ) == tuple(item.kinase for item in load_kinase_transition_catalog().hypotheses)
    assert tuple(
        node.biological_identifier for node in by_kind[FactorGraphNodeKind.SUBTYPE_SIGNATURE_FACTOR]
    ) == ("GPM", "MTC", "NEU", "PPR")


def test_topology_rejects_duplicates_cross_block_edges_and_forged_content() -> None:
    topology = factor_graph_topology()
    payload = topology.model_dump(mode="python")
    payload["nodes"][1]["node_id"] = payload["nodes"][0]["node_id"]
    with pytest.raises(ValidationError, match="node identifiers must be unique"):
        FactorGraphTopology.model_validate(payload)

    payload = topology.model_dump(mode="python")
    payload["containment_edges"][0]["source_node_id"] = "block.phosphosite_sphinks"
    payload["topology_digest"] = topology_payload_digest(payload)
    with pytest.raises(ValidationError, match="cross-block containment is forbidden"):
        FactorGraphTopology.model_validate(payload)

    payload = topology.model_dump(mode="python")
    payload["nodes"][2]["label"] = "forged label"
    with pytest.raises(ValidationError, match="topology digest"):
        FactorGraphTopology.model_validate(payload)


def test_topology_rejects_self_digested_biological_assignment_forgery() -> None:
    topology = factor_graph_topology()
    reactome_index = next(
        index
        for index, node in enumerate(topology.nodes)
        if node.kind is FactorGraphNodeKind.REACTOME_PATHWAY_FACTOR
    )
    kinase_index = next(
        index
        for index, node in enumerate(topology.nodes)
        if node.kind is FactorGraphNodeKind.KINASE_SIGNATURE_FACTOR
    )

    payload = topology.model_dump(mode="python")
    payload["nodes"][reactome_index]["kind"], payload["nodes"][kinase_index]["kind"] = (
        payload["nodes"][kinase_index]["kind"],
        payload["nodes"][reactome_index]["kind"],
    )
    payload["topology_digest"] = topology_payload_digest(payload)
    with pytest.raises(ValidationError, match="factor kinds must remain"):
        FactorGraphTopology.model_validate(payload)

    payload = topology.model_dump(mode="python")
    payload["nodes"][reactome_index]["child_profile_id"] = "wrong-child/9.9.9"
    payload["topology_digest"] = topology_payload_digest(payload)
    with pytest.raises(ValidationError, match="wrong child profile"):
        FactorGraphTopology.model_validate(payload)

    payload = topology.model_dump(mode="python")
    payload["nodes"][reactome_index]["learned_semantics"] = "child_result_container_only"
    payload["topology_digest"] = topology_payload_digest(payload)
    with pytest.raises(ValidationError, match="incompatible learned semantics"):
        FactorGraphTopology.model_validate(payload)

    family_swaps = (
        (
            FactorGraphNodeKind.GLOBAL_RECURRENCE_FACTOR,
            FactorGraphNodeKind.REACTOME_PATHWAY_FACTOR,
        ),
        (
            FactorGraphNodeKind.KINASE_SIGNATURE_FACTOR,
            FactorGraphNodeKind.SUBTYPE_SIGNATURE_FACTOR,
        ),
    )
    for left_kind, right_kind in family_swaps:
        left_index = next(
            index for index, node in enumerate(topology.nodes) if node.kind is left_kind
        )
        right_index = next(
            index for index, node in enumerate(topology.nodes) if node.kind is right_kind
        )
        payload = topology.model_dump(mode="python")
        payload["nodes"][left_index]["kind"], payload["nodes"][right_index]["kind"] = (
            payload["nodes"][right_index]["kind"],
            payload["nodes"][left_index]["kind"],
        )
        payload["topology_digest"] = topology_payload_digest(payload)
        with pytest.raises(ValidationError, match="version-locked biological inventory"):
            FactorGraphTopology.model_validate(payload)


def test_profile_binds_exact_child_artifacts_numpy_topology_and_oracle() -> None:
    profile = algorithm_profile()
    assert profile.topology_digest == factor_graph_topology().topology_digest
    assert profile.composition_semantic_digest == composition_semantic_digest()
    assert profile.numpy_version == "2.5.2"
    assert profile.independent_parallel_blocks is True
    assert profile.cross_modal_fusion_performed is False
    assert profile.no_numerical_cross_block_edges is True
    assert profile.profile_digest == profile_payload_digest(profile)
    assert profile.demo_request_digest == demo_request_digest()
    assert profile.demo_semantic_oracle_digest == demo_semantic_oracle_digest()

    assert profile.reactome_child.model_dump(mode="json") == {
        "block": "protein_reactome",
        "child_profile_id": "kncc-reactome-conditional-transition/1.0.0",
        "child_profile_digest": (
            "sha256:cd987aef30271c4c5479f76e9c63c7454fdc5b2e4576e53439d14d55a8f190ff"
        ),
        "source_digest": (
            "sha256:84732b0bb2c89e82285c7b10fd567c3612eb89ae3a36846df0d7b88b6be59584"
        ),
        "fitted_digest": (
            "sha256:74cb8b63dbdd7d321fb55e1439bb7cf73bfae415edbdd53fab150f06a00dfd7b"
        ),
        "bootstrap_digest": (
            "sha256:53e44131ea0bb159175a889dcfdc07d941f568e59439a807ad5d82fc38707a3f"
        ),
        "evaluation_digest": (
            "sha256:6bf513badfd1c005e70718d98e1dd83c6b987b32596d1f13fc33909f2ce8ea69"
        ),
    }
    assert profile.kinase_child.model_dump(mode="json") == {
        "block": "phosphosite_sphinks",
        "child_profile_id": "kncc-gbm-longitudinal-kinase-transition/1.0.0",
        "child_profile_digest": (
            "sha256:6be719c54fdaf2be0f83cfe649bc9d394454e5eeb187108a0ce0c7feea9f471a"
        ),
        "source_digest": (
            "sha256:3e38ddfc165ff238b7ee8a9c83b16eac799a8d023268319547c47d8eb669fed4"
        ),
        "fitted_digest": (
            "sha256:416a5f814378ed141fc89d3dd4bf497489c472cef2db1c16e97ec9ede080c822"
        ),
        "bootstrap_digest": (
            "sha256:c5756048bce4074efe9b1914c325b0cbb5f312e7840efe92d8b926edbb5df38c"
        ),
        "evaluation_digest": (
            "sha256:303d6694a289f9cb3d181aedc732c2c5679830e9daa33f4098521b8f1cd0aa9e"
        ),
    }
    expected_source_inventory = sha256_digest(
        {
            "reactome_child": profile.reactome_child.model_dump(mode="json"),
            "kinase_child": profile.kinase_child.model_dump(mode="json"),
        }
    )
    assert profile.source_inventory_digest == expected_source_inventory


def test_profile_is_content_bound_and_has_a_locked_composition_digest() -> None:
    profile = algorithm_profile()
    assert profile.profile_digest == (
        "sha256:f325edb99ab6c636be5d5b49f7af3cd8d346d215ff5ec72cb4183ac36b24b33b"
    )
    assert profile.demo_request_digest == (
        "sha256:bee98bde0309065837ab39d2be3eb54ed192ac6242ff3a3b4e4e9efa042b0938"
    )
    assert profile.demo_semantic_oracle_digest == (
        "sha256:72e555d9cc86d955ed3fa47e14586eb999e9b845b1df0625a4eab07f28176f9e"
    )
    payload = profile.model_dump(mode="python")
    payload["reactome_child"]["source_digest"] = ONE_DIGEST
    with pytest.raises(ValidationError, match="source inventory digest"):
        type(profile).model_validate(payload)

    payload["source_inventory_digest"] = sha256_digest(
        {
            "reactome_child": payload["reactome_child"],
            "kinase_child": payload["kinase_child"],
        }
    )
    with pytest.raises(ValidationError, match="profile digest"):
        type(profile).model_validate(payload)

    payload = profile.model_dump(mode="python")
    payload["reactome_child"]["child_profile_id"] = profile.kinase_child.child_profile_id
    payload["source_inventory_digest"] = sha256_digest(
        {
            "reactome_child": payload["reactome_child"],
            "kinase_child": payload["kinase_child"],
        }
    )
    payload["profile_digest"] = profile_payload_digest(payload)
    with pytest.raises(ValidationError, match="Reactome child binding names"):
        type(profile).model_validate(payload)

    payload = profile.model_dump(mode="python")
    payload["source_inventory_digest"] = ONE_DIGEST
    payload["profile_digest"] = profile_payload_digest(payload)
    with pytest.raises(ValidationError, match="source inventory digest"):
        type(profile).model_validate(payload)


def test_profile_wraps_locked_child_failures_as_outer_integrity_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    algorithm_profile.cache_clear()
    monkeypatch.setattr(
        factor_profile_module,
        "reactome_algorithm_profile",
        lambda: (_ for _ in ()).throw(RuntimeError("sensitive child path")),
    )
    with pytest.raises(
        KnccGbmFactorGraphProfileIntegrityError,
        match="locked KNCC child artifact",
    ):
        algorithm_profile()
    algorithm_profile.cache_clear()


def test_verified_result_nests_exact_child_receipts(demo_receipt) -> None:
    request, result = demo_receipt
    assert result.request_digest == request.request_digest
    assert result.profile_digest == algorithm_profile().profile_digest
    assert result.result_digest == result_payload_digest(result)
    assert result.provenance.reactome_child.child_result_digest == (
        result.reactome_result.result_digest
    )
    assert result.provenance.kinase_child.child_result_digest == (
        result.kinase_result.result_digest
    )
    assert result.independent_parallel_blocks is True
    assert result.cross_modal_fusion_performed is False
    assert result.numerical_cross_block_edge_count == 0


def test_unverified_outer_admits_unverified_child_but_verified_outer_rejects_it(
    demo_receipt,
) -> None:
    _, result = demo_receipt
    document = result.model_dump(mode="python")
    document["reactome_result"]["result_digest"] = ZERO_DIGEST
    document["provenance"]["reactome_child"]["child_result_digest"] = ZERO_DIGEST
    document["result_digest"] = ZERO_DIGEST
    unverified = UnverifiedKnccGbmFactorGraphResult.model_validate(document)
    assert isinstance(
        unverified.reactome_result,
        UnverifiedLongitudinalGbmReactomeTransitionResult,
    )
    assert not isinstance(
        unverified.reactome_result,
        type(result.reactome_result),
    )
    assert not isinstance(
        unverified.kinase_result,
        UnverifiedLongitudinalGbmKinaseTransitionResult,
    )
    with pytest.raises(ValidationError, match="result digest"):
        KnccGbmFactorGraphResult.model_validate(document)


def test_result_provenance_rejects_a_child_receipt_binding_mismatch(demo_receipt) -> None:
    _, result = demo_receipt
    document = result.model_dump(mode="python")
    document["provenance"]["kinase_child"]["child_request_digest"] = ONE_DIGEST
    with pytest.raises(ValidationError, match="kinase child result"):
        UnverifiedKnccGbmFactorGraphResult.model_validate(document)


def test_replay_summary_requires_every_independent_check() -> None:
    fields = {
        "verified": True,
        "request_digest_match": True,
        "profile_digest_match": True,
        "topology_digest_match": True,
        "source_inventory_digest_match": True,
        "result_digest_match": True,
        "reactome_child_verified": True,
        "kinase_child_verified": True,
        "independent_parallel_blocks_match": True,
        "no_cross_modal_fusion_match": True,
        "no_numerical_cross_block_edges_match": True,
        "provenance_match": True,
        "document_semantic_match": True,
        "semantic_match": True,
        "recomputed_request_digest": ZERO_DIGEST,
        "recomputed_result_digest": ONE_DIGEST,
        "message": "exact replay",
    }
    replay = KnccGbmFactorGraphReplayVerificationResult(**fields)
    assert replay.verified is True

    broken_semantic = deepcopy(fields)
    broken_semantic["reactome_child_verified"] = False
    with pytest.raises(ValidationError, match="semantic replay summary"):
        KnccGbmFactorGraphReplayVerificationResult(**broken_semantic)

    broken_digest = deepcopy(fields)
    broken_digest["source_inventory_digest_match"] = False
    with pytest.raises(ValidationError, match="verified summary"):
        KnccGbmFactorGraphReplayVerificationResult(**broken_digest)
