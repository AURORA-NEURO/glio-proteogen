"""Runtime, replay, abstention, and fail-closed tests for provisional M22-05."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import pytest

from glio_proteogen.contracts.m22_05 import CoverageStatus, EvaluationStatus
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m22_05_subgroup_equity_evaluator import (
    M2205AuthorizationError,
    M2205ReplayError,
    M2205Service,
    evaluate_protein_rna_discordance_subgroup_equity,
    preflight_m2205_authorization,
)
from tests.contract.test_m22_05_hardening import _request


def test_evaluator_emits_report_and_replays() -> None:
    service = M2205Service()
    result = service.evaluate(_request())
    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert service.replay(result).result_digest == result.result_digest


def test_evaluator_is_deterministic_across_typed_and_json_paths() -> None:
    service = M2205Service()
    request = _request()
    encoded = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    typed = service.evaluate(request)
    parsed = service.evaluate(encoded)
    assert typed.result_digest == parsed.result_digest
    assert evaluate_protein_rna_discordance_subgroup_equity(request).result_digest == (
        typed.result_digest
    )


def test_unsupported_coverage_abstains_without_report() -> None:
    request = _request()
    unsupported = request.coverage[0].model_copy(update={"status": CoverageStatus.UNSUPPORTED})
    result = M2205Service().evaluate(request.model_copy(update={"coverage": (unsupported,)}))
    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.abstention_reason is not None
    assert result.human_review_required is True
    assert M2205Service().replay(result).result_digest == result.result_digest


def test_replay_rejects_identifier_digest_and_request_tampering() -> None:
    service = M2205Service()
    result = service.evaluate(_request())
    with pytest.raises(M2205ReplayError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "m2205-result.tampered"}))
    with pytest.raises(M2205ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    with pytest.raises(M2205ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "a" * 64}))


def test_authorization_fails_closed_before_material_traversal() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    with pytest.raises(M2205AuthorizationError):
        M2205Service().evaluate(request.model_copy(update={"context": context}))


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

    with pytest.raises(M2205AuthorizationError):
        preflight_m2205_authorization(HostileMapping())
