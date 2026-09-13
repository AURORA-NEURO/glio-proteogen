"""Exact branch coverage for the KNCC GBM factor-graph service facade."""

from __future__ import annotations

import pytest

from glio_proteogen.research.kncc_gbm_factor_graph import service as service_module
from glio_proteogen.research.kncc_gbm_factor_graph.contracts import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    KnccGbmFactorGraphReplayVerificationRequest,
    KnccGbmFactorGraphReplayVerificationResult,
    KnccGbmFactorGraphRequest,
    KnccGbmFactorGraphResult,
    UnverifiedKnccGbmFactorGraphResult,
)
from glio_proteogen.research.kncc_gbm_factor_graph.demo import synthetic_demo_request
from glio_proteogen.research.kncc_gbm_factor_graph.errors import (
    KnccGbmFactorGraphInferenceError,
    KnccGbmFactorGraphReplayError,
)
from glio_proteogen.research.kncc_gbm_factor_graph.service import (
    KnccGbmFactorGraphService,
    analyze_kncc_gbm_factor_graph,
    verify_kncc_gbm_factor_graph_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)

ZERO_DIGEST = "sha256:" + "0" * 64


@pytest.fixture(scope="module")
def demo_receipt() -> tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult]:
    request = synthetic_demo_request()
    return request, analyze_kncc_gbm_factor_graph(request)


def _verification_summary(
    request: KnccGbmFactorGraphRequest,
    result: KnccGbmFactorGraphResult,
) -> KnccGbmFactorGraphReplayVerificationResult:
    return KnccGbmFactorGraphReplayVerificationResult(
        verified=True,
        request_digest_match=True,
        profile_digest_match=True,
        topology_digest_match=True,
        source_inventory_digest_match=True,
        result_digest_match=True,
        reactome_child_verified=True,
        kinase_child_verified=True,
        independent_parallel_blocks_match=True,
        no_cross_modal_fusion_match=True,
        no_numerical_cross_block_edges_match=True,
        provenance_match=True,
        document_semantic_match=True,
        semantic_match=True,
        recomputed_request_digest=request.request_digest,
        recomputed_result_digest=result.result_digest,
        message="delegated",
    )


def _forged_recomputed_result(
    result: KnccGbmFactorGraphResult,
) -> KnccGbmFactorGraphResult:
    reactome_result = result.reactome_result.model_copy(
        update={
            "request_digest": ZERO_DIGEST,
            "profile_digest": ZERO_DIGEST,
            "result_digest": ZERO_DIGEST,
            "series_id": "forged.reactome.series",
        }
    )
    kinase_result = result.kinase_result.model_copy(
        update={
            "request_digest": ZERO_DIGEST,
            "profile_digest": ZERO_DIGEST,
            "result_digest": ZERO_DIGEST,
            "series_id": "forged.kinase.series",
        }
    )
    provenance = result.provenance.model_copy(
        update={
            "request_digest": ZERO_DIGEST,
            "profile_digest": ZERO_DIGEST,
            "topology_digest": ZERO_DIGEST,
            "source_inventory_digest": ZERO_DIGEST,
        }
    )
    return result.model_copy(
        update={
            "request_digest": ZERO_DIGEST,
            "profile_digest": ZERO_DIGEST,
            "topology_digest": ZERO_DIGEST,
            "result_digest": ZERO_DIGEST,
            "reactome_result": reactome_result,
            "kinase_result": kinase_result,
            "provenance": provenance,
        }
    )


def _forged_provided_result(
    result: KnccGbmFactorGraphResult,
) -> UnverifiedKnccGbmFactorGraphResult:
    document = result.model_dump(mode="python")
    document["request_digest"] = ZERO_DIGEST
    document["profile_digest"] = ZERO_DIGEST
    document["topology_digest"] = ZERO_DIGEST
    document["result_digest"] = ZERO_DIGEST
    document["analysis_id"] = "forged.outer.analysis"
    document["provenance"]["request_digest"] = ZERO_DIGEST
    document["provenance"]["profile_digest"] = ZERO_DIGEST
    document["provenance"]["topology_digest"] = ZERO_DIGEST
    document["provenance"]["source_inventory_digest"] = ZERO_DIGEST
    for child_name in ("reactome", "kinase"):
        document[f"{child_name}_result"]["result_digest"] = ZERO_DIGEST
        document[f"{child_name}_result"]["series_id"] = f"forged.{child_name}.series"
        document["provenance"][f"{child_name}_child"]["child_result_digest"] = ZERO_DIGEST
    return UnverifiedKnccGbmFactorGraphResult.model_validate(
        document,
        strict=True,
    )


def test_stateless_facade_delegates_both_operations_and_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    demo_receipt: tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult],
) -> None:
    request, result = demo_receipt
    cancellation = CancellationContext()
    analyze_calls: list[tuple[KnccGbmFactorGraphRequest, CancellationContext | None]] = []

    def fake_analyze(
        value: KnccGbmFactorGraphRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> KnccGbmFactorGraphResult:
        analyze_calls.append((value, cancellation))
        return result

    monkeypatch.setattr(service_module, "analyze_kncc_gbm_factor_graph", fake_analyze)
    service = KnccGbmFactorGraphService()
    assert service.analyze(request, cancellation=cancellation) is result
    assert analyze_calls == [(request, cancellation)]

    verification = KnccGbmFactorGraphReplayVerificationRequest(
        request=request,
        result=result,
    )
    expected = _verification_summary(request, result)
    verify_calls: list[
        tuple[KnccGbmFactorGraphReplayVerificationRequest, CancellationContext | None]
    ] = []

    def fake_verify(
        value: KnccGbmFactorGraphReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> KnccGbmFactorGraphReplayVerificationResult:
        verify_calls.append((value, cancellation))
        return expected

    monkeypatch.setattr(
        service_module,
        "verify_kncc_gbm_factor_graph_replay",
        fake_verify,
    )
    assert service.verify(verification, cancellation=cancellation) is expected
    assert verify_calls == [(verification, cancellation)]


def test_request_size_guard_stops_before_child_inference(
    monkeypatch: pytest.MonkeyPatch,
    demo_receipt: tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult],
) -> None:
    request, result = demo_receipt
    inference_calls: list[tuple[KnccGbmFactorGraphRequest, CancellationContext | None]] = []

    def fake_infer(
        value: KnccGbmFactorGraphRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> KnccGbmFactorGraphResult:
        inference_calls.append((value, cancellation))
        return result

    monkeypatch.setattr(service_module, "_encoded_size", lambda _value: MAX_REQUEST_BYTES + 1)
    monkeypatch.setattr(service_module, "infer_kncc_gbm_factor_graph", fake_infer)

    with pytest.raises(KnccGbmFactorGraphInferenceError, match="request exceeds 4 MiB"):
        analyze_kncc_gbm_factor_graph(request)
    assert not inference_calls


def test_result_size_guard_runs_after_one_child_inference(
    monkeypatch: pytest.MonkeyPatch,
    demo_receipt: tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult],
) -> None:
    request, result = demo_receipt
    sizes = iter((MAX_REQUEST_BYTES, MAX_RESULT_BYTES + 1))
    inference_calls: list[tuple[KnccGbmFactorGraphRequest, CancellationContext | None]] = []

    def fake_infer(
        value: KnccGbmFactorGraphRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> KnccGbmFactorGraphResult:
        inference_calls.append((value, cancellation))
        return result

    monkeypatch.setattr(service_module, "_encoded_size", lambda _value: next(sizes))
    monkeypatch.setattr(service_module, "infer_kncc_gbm_factor_graph", fake_infer)

    with pytest.raises(KnccGbmFactorGraphInferenceError, match="result exceeds 8 MiB"):
        analyze_kncc_gbm_factor_graph(request)
    assert inference_calls == [(request, None)]


def test_replay_size_guard_stops_before_recomputation(
    monkeypatch: pytest.MonkeyPatch,
    demo_receipt: tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult],
) -> None:
    request, result = demo_receipt
    verification = KnccGbmFactorGraphReplayVerificationRequest(
        request=request,
        result=result,
    )
    recompute_calls: list[tuple[KnccGbmFactorGraphRequest, CancellationContext | None]] = []

    def fake_analyze(
        value: KnccGbmFactorGraphRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> KnccGbmFactorGraphResult:
        recompute_calls.append((value, cancellation))
        return result

    monkeypatch.setattr(service_module, "_encoded_size", lambda _value: MAX_REPLAY_BYTES + 1)
    monkeypatch.setattr(service_module, "analyze_kncc_gbm_factor_graph", fake_analyze)

    with pytest.raises(KnccGbmFactorGraphReplayError, match="replay envelope exceeds 16 MiB"):
        verify_kncc_gbm_factor_graph_replay(verification)
    assert not recompute_calls


def test_cancelled_calls_stop_before_inference_or_recomputation(
    monkeypatch: pytest.MonkeyPatch,
    demo_receipt: tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult],
) -> None:
    request, result = demo_receipt
    cancellation = CancellationContext()
    cancellation.cancel()
    calls: list[tuple[KnccGbmFactorGraphRequest, CancellationContext | None]] = []

    def fail_if_called(
        value: KnccGbmFactorGraphRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> KnccGbmFactorGraphResult:
        calls.append((value, cancellation))
        return result

    monkeypatch.setattr(service_module, "infer_kncc_gbm_factor_graph", fail_if_called)
    with pytest.raises(InferenceCancelledError, match="inference was cancelled"):
        analyze_kncc_gbm_factor_graph(request, cancellation=cancellation)

    monkeypatch.setattr(service_module, "analyze_kncc_gbm_factor_graph", fail_if_called)
    verification = KnccGbmFactorGraphReplayVerificationRequest(
        request=request,
        result=result,
    )
    with pytest.raises(InferenceCancelledError, match="inference was cancelled"):
        verify_kncc_gbm_factor_graph_replay(verification, cancellation=cancellation)
    assert not calls


def test_analysis_propagates_sanitized_child_inference_errors(
    monkeypatch: pytest.MonkeyPatch,
    demo_receipt: tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult],
) -> None:
    request, _ = demo_receipt
    failure_message = "sanitized child failure"

    def fail_inference(
        value: KnccGbmFactorGraphRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> KnccGbmFactorGraphResult:
        assert value == request
        assert cancellation is None
        raise KnccGbmFactorGraphInferenceError(failure_message)

    monkeypatch.setattr(service_module, "infer_kncc_gbm_factor_graph", fail_inference)
    with pytest.raises(KnccGbmFactorGraphInferenceError, match="sanitized child failure"):
        analyze_kncc_gbm_factor_graph(request)


def test_replay_reports_every_mismatch_in_a_forged_provided_receipt(
    monkeypatch: pytest.MonkeyPatch,
    demo_receipt: tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult],
) -> None:
    request, result = demo_receipt
    forged = _forged_provided_result(result)
    monkeypatch.setattr(
        service_module,
        "analyze_kncc_gbm_factor_graph",
        lambda _request, *, cancellation=None: result,
    )

    checked = verify_kncc_gbm_factor_graph_replay(
        KnccGbmFactorGraphReplayVerificationRequest(request=request, result=forged)
    )

    assert not checked.verified
    assert not checked.request_digest_match
    assert not checked.profile_digest_match
    assert not checked.topology_digest_match
    assert not checked.source_inventory_digest_match
    assert not checked.result_digest_match
    assert not checked.reactome_child_verified
    assert not checked.kinase_child_verified
    assert checked.independent_parallel_blocks_match
    assert checked.no_cross_modal_fusion_match
    assert checked.no_numerical_cross_block_edges_match
    assert not checked.provenance_match
    assert not checked.document_semantic_match
    assert not checked.semantic_match
    assert "differs" in checked.message


def test_replay_reports_every_mismatch_in_a_forged_recomputed_receipt(
    monkeypatch: pytest.MonkeyPatch,
    demo_receipt: tuple[KnccGbmFactorGraphRequest, KnccGbmFactorGraphResult],
) -> None:
    request, result = demo_receipt
    forged = _forged_recomputed_result(result)
    monkeypatch.setattr(
        service_module,
        "analyze_kncc_gbm_factor_graph",
        lambda _request, *, cancellation=None: forged,
    )

    checked = verify_kncc_gbm_factor_graph_replay(
        KnccGbmFactorGraphReplayVerificationRequest(request=request, result=result)
    )

    assert not checked.verified
    assert not checked.request_digest_match
    assert not checked.profile_digest_match
    assert not checked.topology_digest_match
    assert not checked.source_inventory_digest_match
    assert not checked.result_digest_match
    assert not checked.reactome_child_verified
    assert not checked.kinase_child_verified
    assert checked.independent_parallel_blocks_match
    assert checked.no_cross_modal_fusion_match
    assert checked.no_numerical_cross_block_edges_match
    assert not checked.provenance_match
    assert not checked.document_semantic_match
    assert not checked.semantic_match
    assert "differs" in checked.message
