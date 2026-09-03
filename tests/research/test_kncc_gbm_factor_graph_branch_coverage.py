"""Adversarial branch coverage for the KNCC GBM factor-graph core."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.research.kncc_gbm_factor_graph import engine as engine_module
from glio_proteogen.research.kncc_gbm_factor_graph import profile as profile_module
from glio_proteogen.research.kncc_gbm_factor_graph.contracts import (
    FactorGraphBlock,
    FactorGraphNodeKind,
    FactorGraphTopology,
    KnccGbmFactorGraphResult,
)
from glio_proteogen.research.kncc_gbm_factor_graph.demo import synthetic_demo_request
from glio_proteogen.research.kncc_gbm_factor_graph.errors import (
    KnccGbmFactorGraphInferenceError,
    KnccGbmFactorGraphProfileIntegrityError,
)
from glio_proteogen.research.kncc_gbm_factor_graph.profile import algorithm_profile
from glio_proteogen.research.kncc_gbm_factor_graph.service import (
    analyze_kncc_gbm_factor_graph,
)
from glio_proteogen.research.kncc_gbm_factor_graph.topology import factor_graph_topology

if TYPE_CHECKING:
    from collections.abc import Callable

ZERO_DIGEST = "sha256:" + "0" * 64


@pytest.fixture(scope="module")
def analyzed_demo() -> KnccGbmFactorGraphResult:
    return analyze_kncc_gbm_factor_graph(synthetic_demo_request())


def _node_index(topology: FactorGraphTopology, kind: FactorGraphNodeKind) -> int:
    return next(index for index, node in enumerate(topology.nodes) if node.kind is kind)


def _assert_topology_validation_error(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        FactorGraphTopology.model_validate(payload, strict=True)


def _call_validator(model: object, method_name: str, *args: object) -> object:
    validator = cast("Callable[..., object]", getattr(model, method_name))
    return validator(*args)


def test_topology_rejects_remaining_invalid_node_and_edge_shapes() -> None:
    topology = factor_graph_topology()
    global_index = _node_index(topology, FactorGraphNodeKind.GLOBAL_RECURRENCE_FACTOR)
    pathway_index = _node_index(topology, FactorGraphNodeKind.REACTOME_PATHWAY_FACTOR)
    kinase_index = _node_index(topology, FactorGraphNodeKind.KINASE_SIGNATURE_FACTOR)

    payload = topology.model_dump(mode="python")
    payload["containment_edges"][1]["edge_id"] = payload["containment_edges"][0]["edge_id"]
    _assert_topology_validation_error(payload, "containment-edge identifiers must be unique")

    payload = topology.model_dump(mode="python")
    payload["nodes"][pathway_index]["kind"] = FactorGraphNodeKind.GLOBAL_RECURRENCE_FACTOR
    _assert_topology_validation_error(payload, "node-family counts")

    payload = topology.model_dump(mode="python")
    payload["nodes"][global_index]["block"] = FactorGraphBlock.PHOSPHOSITE_SPHINKS
    _assert_topology_validation_error(payload, "Reactome factor kinds must remain")

    payload = topology.model_dump(mode="python")
    payload["nodes"][1]["block"] = FactorGraphBlock.PROTEIN_REACTOME
    payload["nodes"][1]["child_profile_id"] = payload["nodes"][0]["child_profile_id"]
    _assert_topology_validation_error(payload, "exactly one node for each block")

    payload = topology.model_dump(mode="python")
    payload["containment_edges"][0]["target_node_id"] = "unknown.factor"
    _assert_topology_validation_error(payload, "references an unknown factor-graph node")

    payload = topology.model_dump(mode="python")
    payload["containment_edges"][0]["source_node_id"] = topology.nodes[pathway_index].node_id
    _assert_topology_validation_error(payload, "must originate at computation-block nodes")

    payload = topology.model_dump(mode="python")
    payload["containment_edges"][0]["target_node_id"] = topology.nodes[0].node_id
    _assert_topology_validation_error(payload, "computation-block nodes cannot be")

    payload = topology.model_dump(mode="python")
    payload["containment_edges"][1]["target_node_id"] = payload["containment_edges"][0][
        "target_node_id"
    ]
    _assert_topology_validation_error(payload, "exactly one containment parent")

    # Keep the otherwise-unused index honest: it also establishes that both blocks
    # contain a factor node before the structural corruptions above are attempted.
    assert topology.nodes[kinase_index].block is FactorGraphBlock.PHOSPHOSITE_SPHINKS


def test_topology_validator_rejects_corrupted_copies_that_bypass_field_validation() -> None:
    topology = factor_graph_topology()

    missing_parent = topology.model_copy(
        update={"containment_edges": topology.containment_edges[:-1]}
    )
    with pytest.raises(ValueError, match="every non-block factor"):
        _call_validator(missing_parent, "topology_is_complete_and_content_bound")

    forbidden_cross_edge = topology.model_copy(
        update={"cross_block_edges": (topology.containment_edges[0],)}
    )
    with pytest.raises(ValueError, match="cross-block edges are forbidden"):
        _call_validator(forbidden_cross_edge, "topology_is_complete_and_content_bound")


def test_profile_rejects_remaining_outer_and_child_binding_mismatches() -> None:
    profile = algorithm_profile()

    wrong_topology_digest = profile.model_copy(update={"topology_digest": ZERO_DIGEST})
    with pytest.raises(ValueError, match="embedded topology"):
        _call_validator(wrong_topology_digest, "profile_is_complete_and_content_bound")

    wrong_reactome_block = profile.model_copy(
        update={
            "reactome_child": profile.reactome_child.model_copy(
                update={"block": FactorGraphBlock.PHOSPHOSITE_SPHINKS}
            )
        }
    )
    with pytest.raises(ValueError, match="Reactome child binding is assigned"):
        _call_validator(wrong_reactome_block, "profile_is_complete_and_content_bound")

    wrong_kinase_block = profile.model_copy(
        update={
            "kinase_child": profile.kinase_child.model_copy(
                update={"block": FactorGraphBlock.PROTEIN_REACTOME}
            )
        }
    )
    with pytest.raises(ValueError, match="kinase child binding is assigned"):
        _call_validator(wrong_kinase_block, "profile_is_complete_and_content_bound")

    wrong_kinase_profile = profile.model_copy(
        update={
            "kinase_child": profile.kinase_child.model_copy(
                update={"child_profile_id": profile.reactome_child.child_profile_id}
            )
        }
    )
    with pytest.raises(ValueError, match="kinase child binding names"):
        _call_validator(wrong_kinase_profile, "profile_is_complete_and_content_bound")

    topology_nodes = list(profile.topology.nodes)
    topology_nodes[0] = topology_nodes[0].model_copy(
        update={"child_profile_id": profile.kinase_child.child_profile_id}
    )
    wrong_topology_binding = profile.model_copy(
        update={"topology": profile.topology.model_copy(update={"nodes": tuple(topology_nodes)})}
    )
    with pytest.raises(ValueError, match="topology nodes disagree"):
        _call_validator(wrong_topology_binding, "profile_is_complete_and_content_bound")


def test_provenance_rejects_each_wrong_child_block(
    analyzed_demo: KnccGbmFactorGraphResult,
) -> None:
    provenance = analyzed_demo.provenance

    wrong_reactome = provenance.model_copy(
        update={
            "reactome_child": provenance.reactome_child.model_copy(
                update={"block": FactorGraphBlock.PHOSPHOSITE_SPHINKS}
            )
        }
    )
    with pytest.raises(ValueError, match="Reactome provenance"):
        _call_validator(wrong_reactome, "child_blocks_are_distinct")

    wrong_kinase = provenance.model_copy(
        update={
            "kinase_child": provenance.kinase_child.model_copy(
                update={"block": FactorGraphBlock.PROTEIN_REACTOME}
            )
        }
    )
    with pytest.raises(ValueError, match="kinase provenance"):
        _call_validator(wrong_kinase, "child_blocks_are_distinct")


def test_result_document_rejects_outer_child_and_resource_binding_mismatches(
    analyzed_demo: KnccGbmFactorGraphResult,
) -> None:
    reactome_result = analyzed_demo.reactome_result
    kinase_result = analyzed_demo.kinase_result

    wrong_profile = analyzed_demo.model_copy(update={"profile_digest": ZERO_DIGEST})
    with pytest.raises(ValueError, match="profile digest does not match provenance"):
        wrong_profile._validate_outer_and_child_bindings(reactome_result, kinase_result)

    wrong_topology = analyzed_demo.model_copy(update={"topology_digest": ZERO_DIGEST})
    with pytest.raises(ValueError, match="topology digest does not match provenance"):
        wrong_topology._validate_outer_and_child_bindings(reactome_result, kinase_result)

    wrong_request = analyzed_demo.model_copy(update={"request_digest": ZERO_DIGEST})
    with pytest.raises(ValueError, match="request digest does not match provenance"):
        wrong_request._validate_outer_and_child_bindings(reactome_result, kinase_result)

    provenance = analyzed_demo.provenance.model_copy(
        update={
            "reactome_child": analyzed_demo.provenance.reactome_child.model_copy(
                update={"child_result_digest": ZERO_DIGEST}
            )
        }
    )
    wrong_reactome_binding = analyzed_demo.model_copy(update={"provenance": provenance})
    with pytest.raises(ValueError, match="Reactome child result"):
        wrong_reactome_binding._validate_outer_and_child_bindings(reactome_result, kinase_result)

    six_reactome_ids = (*reactome_result.time_point_ids, "reactome.extra.4", "reactome.extra.5")
    oversized_reactome = reactome_result.model_copy(update={"time_point_ids": six_reactome_ids})
    with pytest.raises(ValueError, match="Reactome child result exceeds"):
        analyzed_demo._validate_outer_and_child_bindings(oversized_reactome, kinase_result)

    six_kinase_ids = (*kinase_result.time_point_ids, "kinase.extra.4", "kinase.extra.5")
    oversized_kinase = kinase_result.model_copy(update={"time_point_ids": six_kinase_ids})
    with pytest.raises(ValueError, match="kinase child result exceeds"):
        analyzed_demo._validate_outer_and_child_bindings(reactome_result, oversized_kinase)

    wrong_result_digest = analyzed_demo.model_copy(update={"result_digest": ZERO_DIGEST})
    with pytest.raises(ValueError, match="result digest does not match canonical"):
        _call_validator(wrong_result_digest, "result_is_exactly_nested_and_content_bound")


def test_engine_rejects_each_child_receipt_binding_failure(
    analyzed_demo: KnccGbmFactorGraphResult,
) -> None:
    profile = algorithm_profile()
    reactome_result = analyzed_demo.reactome_result

    with pytest.raises(KnccGbmFactorGraphProfileIntegrityError, match="wrong child block"):
        engine_module._bind_child_result(
            block=FactorGraphBlock.PHOSPHOSITE_SPHINKS,
            result=reactome_result,
            expected=profile.reactome_child,
            expected_request_digest=reactome_result.request_digest,
        )

    wrong_profile = profile.reactome_child.model_copy(update={"child_profile_digest": ZERO_DIGEST})
    with pytest.raises(KnccGbmFactorGraphProfileIntegrityError, match="locked child profile"):
        engine_module._bind_child_result(
            block=FactorGraphBlock.PROTEIN_REACTOME,
            result=reactome_result,
            expected=wrong_profile,
            expected_request_digest=reactome_result.request_digest,
        )

    with pytest.raises(KnccGbmFactorGraphInferenceError, match="supplied child request"):
        engine_module._bind_child_result(
            block=FactorGraphBlock.PROTEIN_REACTOME,
            result=reactome_result,
            expected=profile.reactome_child,
            expected_request_digest=ZERO_DIGEST,
        )


def test_profile_builder_rejects_an_incompatible_numpy_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(profile_module, "EXPECTED_NUMPY_VERSION", "2.5.1")
    with pytest.raises(RuntimeError, match=r"requires NumPy 2\.5\.2"):
        profile_module._build_algorithm_profile()


def test_profile_integrity_errors_are_reraised_without_resanitizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = KnccGbmFactorGraphProfileIntegrityError("specific outer integrity failure")

    def fail_with_integrity_error() -> KnccGbmFactorGraphResult:
        raise sentinel

    algorithm_profile.cache_clear()
    monkeypatch.setattr(profile_module, "_build_algorithm_profile", fail_with_integrity_error)
    with pytest.raises(KnccGbmFactorGraphProfileIntegrityError) as caught:
        algorithm_profile()
    assert caught.value is sentinel
    algorithm_profile.cache_clear()
