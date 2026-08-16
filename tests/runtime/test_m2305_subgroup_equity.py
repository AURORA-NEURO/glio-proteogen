"""Runtime, replay, abstention, and fail-closed tests for provisional M23-05."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import pytest

from glio_proteogen.contracts.m23_05 import CoverageStatus, EquityStatus, EvaluationStatus
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m23_05_subgroup_equity_evaluator import (
    M2305AuthorizationError,
    M2305ReplayError,
    M2305Service,
    evaluate_variant_peptide_subgroup_equity,
    preflight_m2305_authorization,
)
from tests.contract.test_m23_05_hardening import _request

_REQUIRED_DIMENSION_COUNT = 8
_CONTROL_COUNT = 7


def test_evaluator_emits_report_and_replays() -> None:
    service = M2305Service()
    result = service.evaluate(_request())
    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert len(result.report.performance) == _REQUIRED_DIMENSION_COUNT
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert service.replay(result).result_digest == result.result_digest


def test_evaluator_is_deterministic_across_typed_and_json_paths() -> None:
    service = M2305Service()
    request = _request()
    encoded = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    typed = service.evaluate(request)
    parsed = service.evaluate(encoded)
    assert typed.result_digest == parsed.result_digest
    assert evaluate_variant_peptide_subgroup_equity(request).result_digest == typed.result_digest


@pytest.mark.parametrize("field", ["coverage", "performance", "equity", "calibration"])
def test_unsupported_material_abstains_without_report(field: str) -> None:
    request = _request()
    if field == "coverage":
        coverage_item = request.coverage[0].model_copy(
            update={"status": CoverageStatus.UNSUPPORTED}
        )
        request = request.model_copy(update={"coverage": (coverage_item, *request.coverage[1:])})
    elif field == "performance":
        performance_item = request.performance[0].model_copy(
            update={"coverage_status": CoverageStatus.UNSUPPORTED}
        )
        request = request.model_copy(
            update={"performance": (performance_item, *request.performance[1:])}
        )
    elif field == "equity":
        equity_item = request.performance[0].model_copy(
            update={"equity_status": EquityStatus.RESTRICTED}
        )
        request = request.model_copy(
            update={"performance": (equity_item, *request.performance[1:])}
        )
    else:
        calibration_item = request.calibration[0].model_copy(
            update={"status": EvaluationStatus.ABSTAINED}
        )
        request = request.model_copy(
            update={"calibration": (calibration_item, *request.calibration[1:])}
        )
    result = M2305Service().evaluate(request)
    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.abstention_reason is not None
    assert result.human_review_required is True
    assert M2305Service().replay(result).result_digest == result.result_digest


def test_replay_rejects_identifier_digest_and_request_tampering() -> None:
    service = M2305Service()
    result = service.evaluate(_request())
    with pytest.raises(M2305ReplayError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "m2305-result.tampered"}))
    with pytest.raises(M2305ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    with pytest.raises(M2305ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "a" * 64}))


def test_authorization_fails_closed_before_material_traversal() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    with pytest.raises(M2305AuthorizationError):
        M2305Service().evaluate(request.model_copy(update={"context": context}))


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

    with pytest.raises(M2305AuthorizationError):
        preflight_m2305_authorization(HostileMapping())
