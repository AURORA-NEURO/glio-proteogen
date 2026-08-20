"""Runtime and replay tests for provisional M21-03."""

from __future__ import annotations

import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m21_03_internal_benchmark_ablation import (
    M2103AuthorizationError,
    M2103ReplayError,
    M2103Service,
    preflight_m2103_authorization,
    run_complex_activity_internal_benchmark,
)
from tests.contract.test_m21_03_provisional import _request


def test_runtime_is_deterministic_and_replay_verifiable() -> None:
    request = _request()
    service = M2103Service()
    first = service.generate(request)
    second = service.generate(request)
    assert first.result_digest == second.result_digest
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert service.replay(first).result_digest == first.result_digest
    assert first.dossier is not None
    assert first.dossier.split == request.split
    assert first.dossier.baselines == request.baseline_runs
    assert run_complex_activity_internal_benchmark(request).result_digest == first.result_digest


def test_provenance_covers_nested_benchmark_evidence() -> None:
    request = _request()
    result = M2103Service().generate(request)
    nested_evidence = (
        *request.split.evidence,
        *(item for baseline in request.baseline_runs for item in baseline.evidence),
        *(
            item
            for baseline in request.baseline_runs
            for metric in baseline.metrics
            for item in metric.evidence
        ),
        *(item for ablation in request.ablations for item in ablation.evidence),
        *(item for comparison in request.comparisons for item in comparison.evidence),
    )

    assert {item.reference.digest for item in nested_evidence} <= set(
        result.provenance.input_digests
    )


def test_runtime_rejects_denied_controls_before_benchmarking() -> None:
    request = _request()
    rejected_support = request.context.references.support.model_copy(update={"state": "rejected"})
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={"support": rejected_support}
            )
        }
    )
    with pytest.raises(M2103AuthorizationError, match="requires accepted"):
        M2103Service().generate(request.model_copy(update={"context": denied_context}))


def test_runtime_rejects_tampered_replay_digest() -> None:
    service = M2103Service()
    result = service.generate(_request())
    with pytest.raises(M2103ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))


def test_runtime_replay_rejects_request_and_identifier_tampering() -> None:
    service = M2103Service()
    result = service.generate(_request())
    with pytest.raises(M2103ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "e" * 64}))
    with pytest.raises(M2103ReplayError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "m2103.result.tampered"}))
    with pytest.raises(M2103AuthorizationError):
        preflight_m2103_authorization({})
