"""Focused lifecycle tests for the independent KNCC GBM factor graph."""

from __future__ import annotations

import pytest

from glio_proteogen.research.kncc_gbm_factor_graph import service as service_module
from glio_proteogen.research.kncc_gbm_factor_graph.contracts import (
    DEMO_ID,
    KnccGbmFactorGraphReplayVerificationRequest,
    KnccGbmFactorGraphResult,
    UnverifiedKnccGbmFactorGraphResult,
)
from glio_proteogen.research.kncc_gbm_factor_graph.demo import (
    demo_request_digest,
    demo_semantic_oracle_digest,
    synthetic_demo_request,
)
from glio_proteogen.research.kncc_gbm_factor_graph.profile import algorithm_profile
from glio_proteogen.research.kncc_gbm_factor_graph.service import (
    analyze_kncc_gbm_factor_graph,
    verify_kncc_gbm_factor_graph_replay,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.canonical import (
    canonical_request_digest as canonical_kinase_request_digest,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.demo import (
    synthetic_demo_request as synthetic_kinase_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.canonical import (
    canonical_request_digest as canonical_reactome_request_digest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    synthetic_demo_request as synthetic_reactome_demo_request,
)


@pytest.fixture(scope="module")
def analyzed_demo() -> KnccGbmFactorGraphResult:
    return analyze_kncc_gbm_factor_graph(synthetic_demo_request())


def test_demo_is_the_exact_composition_bound_by_the_profile() -> None:
    request = synthetic_demo_request()
    profile = algorithm_profile()

    assert request.analysis_id == DEMO_ID
    assert request.reactome_request == synthetic_reactome_demo_request()
    assert request.kinase_request == synthetic_kinase_demo_request()
    assert demo_request_digest() == request.request_digest == profile.demo_request_digest
    assert demo_semantic_oracle_digest() == profile.demo_semantic_oracle_digest


def test_analysis_preserves_child_receipts_without_fusion(
    analyzed_demo: KnccGbmFactorGraphResult,
) -> None:
    request = synthetic_demo_request()
    profile = algorithm_profile()

    assert analyzed_demo.profile_digest == profile.profile_digest
    assert analyzed_demo.topology_digest == profile.topology_digest
    assert analyzed_demo.provenance.source_inventory_digest == profile.source_inventory_digest
    assert analyzed_demo.reactome_result.request_digest == canonical_reactome_request_digest(
        request.reactome_request
    )
    assert analyzed_demo.kinase_result.request_digest == canonical_kinase_request_digest(
        request.kinase_request
    )
    assert analyzed_demo.reactome_result.output_semantics == (
        "global_recurrence_concordance_and_conditional_pathway_concordance_only"
    )
    assert (
        analyzed_demo.kinase_result.output_semantics
        == "SPHINKS_signature_transition_concordance_only"
    )
    assert analyzed_demo.independent_parallel_blocks is True
    assert analyzed_demo.cross_modal_fusion_performed is False
    assert analyzed_demo.numerical_cross_block_edge_count == 0
    assert profile.topology.cross_block_edges == ()


def test_replay_checks_each_child_and_every_outer_binding(
    analyzed_demo: KnccGbmFactorGraphResult,
) -> None:
    checked = verify_kncc_gbm_factor_graph_replay(
        KnccGbmFactorGraphReplayVerificationRequest(
            request=synthetic_demo_request(),
            result=analyzed_demo,
        )
    )

    assert checked.verified
    assert checked.request_digest_match
    assert checked.profile_digest_match
    assert checked.topology_digest_match
    assert checked.source_inventory_digest_match
    assert checked.result_digest_match
    assert checked.reactome_child_verified
    assert checked.kinase_child_verified
    assert checked.independent_parallel_blocks_match
    assert checked.no_cross_modal_fusion_match
    assert checked.no_numerical_cross_block_edges_match
    assert checked.provenance_match
    assert checked.document_semantic_match
    assert checked.semantic_match


def test_outer_digest_forgery_fails_without_obscuring_valid_children(
    monkeypatch: pytest.MonkeyPatch,
    analyzed_demo: KnccGbmFactorGraphResult,
) -> None:
    document = analyzed_demo.model_dump(mode="python")
    document["result_digest"] = "sha256:" + "0" * 64
    forged = UnverifiedKnccGbmFactorGraphResult.model_validate(document, strict=True)
    calls: list[object] = []

    def return_recomputed(
        request: object,
        *,
        cancellation: object = None,
    ) -> KnccGbmFactorGraphResult:
        calls.append((request, cancellation))
        return analyzed_demo

    monkeypatch.setattr(
        service_module,
        "analyze_kncc_gbm_factor_graph",
        return_recomputed,
    )
    checked = verify_kncc_gbm_factor_graph_replay(
        KnccGbmFactorGraphReplayVerificationRequest(
            request=synthetic_demo_request(),
            result=forged,
        )
    )

    assert len(calls) == 1
    assert not checked.verified
    assert not checked.result_digest_match
    assert checked.reactome_child_verified
    assert checked.kinase_child_verified
    assert checked.semantic_match
