"""Runtime, replay, and fail-closed preflight tests for provisional M22-03."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import pytest

from glio_proteogen.contracts.m22_03 import BenchmarkStatus
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m22_03_internal_benchmark_ablation import (
    M2203AuthorizationError,
    M2203ReplayError,
    M2203Service,
    preflight_m2203_authorization,
    run_protein_rna_discordance_internal_benchmark,
)
from tests.contract.test_m22_03_hardening import _request


def test_benchmark_emits_dossier_and_replays() -> None:
    service = M2203Service()
    result = service.generate(_request())
    assert result.status is BenchmarkStatus.COMPLETED
    assert result.dossier is not None
    assert service.replay(result).result_digest == result.result_digest


def test_benchmark_is_deterministic_across_typed_and_json_paths() -> None:
    service = M2203Service()
    request = _request()
    encoded = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    typed = service.generate(request)
    parsed = service.generate(encoded)
    assert typed.result_digest == parsed.result_digest
    assert run_protein_rna_discordance_internal_benchmark(request).result_digest == (
        typed.result_digest
    )


def test_replay_rejects_identifier_digest_and_request_tampering() -> None:
    service = M2203Service()
    result = service.generate(_request())
    with pytest.raises(M2203ReplayError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "m2203.result.tampered"}))
    with pytest.raises(M2203ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    with pytest.raises(M2203ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "a" * 64}))


def test_authorization_fails_closed_before_material_traversal() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    with pytest.raises(M2203AuthorizationError):
        M2203Service().generate(request.model_copy(update={"context": context}))


def test_hostile_mapping_fails_closed() -> None:
    class HostileMapping(Mapping[str, object]):
        def get(self, _field: str, _default: object = None) -> object:
            raise RuntimeError("hostile mapping")  # noqa: TRY003

        def __getitem__(self, _key: str) -> object:
            raise RuntimeError("hostile mapping")  # noqa: TRY003

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

    with pytest.raises(M2203AuthorizationError):
        preflight_m2203_authorization(HostileMapping())
