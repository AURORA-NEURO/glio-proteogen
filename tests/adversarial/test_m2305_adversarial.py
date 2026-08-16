"""Deep adversarial closure for M23-05 runtime and interface boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m23_05.fixture import denied_request, restricted_request, unsupported_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m23_05 import (
    CoverageSummary,
    EvaluationStatus,
    canonical_request_digest,
    normalized_request,
    result_identifier,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import SupportDecision, SupportStatus
from glio_proteogen.modules.c21_reference_material.m23_05_subgroup_equity_evaluator import (
    EquityEvaluationSubmission,
    M2305AuthorizationError,
    M2305Plugin,
    M2305Service,
    cli_app,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m23_05_subgroup_equity_evaluator import (
    cli as cli_module,
)
from tests.contract.test_m23_05_hardening import (
    _completed_result,
    _coverage,
    _request,
    _request_update,
    _result_update,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_UNPROCESSABLE = 422


def test_canonical_dict_projection_and_identity_are_stable() -> None:
    request = _request()
    document = normalized_request(request)
    assert canonical_request_digest(document) == canonical_request_digest(request)
    assert result_identifier(document) == result_identifier(request)


def test_bounds_and_coverage_arithmetic_reject_adversarial_values() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="within bounds"):
        _request_update(
            request,
            performance=(
                request.performance[0].model_copy(update={"value": 0.9}),
                *request.performance[1:],
            ),
        )
    with pytest.raises(ValidationError, match="supported examples"):
        CoverageSummary.model_validate(
            _coverage(request.performance[0].dimension).model_dump(mode="python")
            | {"supported_examples": 11},
            strict=True,
        )


def test_engine_abstains_for_restricted_and_unsupported_material() -> None:
    service = M2305Service()
    for request in (unsupported_request(), restricted_request()):
        result = service.evaluate(request)
        assert result.status is EvaluationStatus.ABSTAINED
        assert result.report is None
        assert result.human_review_required is True


def test_result_digest_request_and_status_closures_reject_tampering() -> None:
    request = _request()
    result = _completed_result(request)
    with pytest.raises(ValidationError, match="request digest"):
        _result_update(result, request_digest=sha256_digest("wrong"))
    with pytest.raises(ValidationError, match="evaluated result"):
        _result_update(result, report=None)
    with pytest.raises(ValidationError, match="abstained result"):
        _result_update(
            result,
            status=EvaluationStatus.ABSTAINED,
            report=None,
            abstention_reason=None,
            support_decision=SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="unsupported",
                rationale="unsupported",
            ),
        )


def test_fastapi_non_object_replay_is_sanitized() -> None:
    response = TestClient(create_app(M2305Service())).post(
        "/v1/modules/M23-05/verify", content=b"[]"
    )
    assert response.status_code == _HTTP_UNPROCESSABLE


def test_plugin_typed_submission_and_cli_stdout_paths(tmp_path: Path) -> None:
    request = _request()
    plugin = M2305Plugin(M2305Service())
    validated = plugin.validate(EquityEvaluationSubmission(request=request))
    assert plugin.run(validated).result_digest.startswith("sha256:")
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "request"]).exit_code == 0
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(bad)]).exit_code != 0


def test_cli_abstention_denial_and_replay_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    denied = tmp_path / "denied.json"
    denied.write_bytes(denied_request().model_dump_json().encode())
    assert runner.invoke(cli_app, ["validate", str(denied)]).exit_code != 0
    assert runner.invoke(cli_app, ["evaluate", str(denied)]).exit_code != 0
    unsupported = tmp_path / "unsupported.json"
    unsupported.write_bytes(unsupported_request().model_dump_json().encode())
    assert runner.invoke(cli_app, ["evaluate", str(unsupported)]).exit_code != 0
    valid = tmp_path / "valid.json"
    valid.write_bytes(_completed_result(_request()).model_dump_json().encode())

    class Mismatch:
        result_digest = "sha256:" + "0" * 64

    class Service:
        def replay(self, _result: object) -> Mismatch:
            return Mismatch()

    monkeypatch.setattr(cli_module, "_SERVICE", Service())
    assert runner.invoke(cli_app, ["verify", str(valid)]).exit_code != 0


def test_authentication_denial_is_not_recast_as_a_negative_equity_result() -> None:
    with pytest.raises(M2305AuthorizationError):
        M2305Service().evaluate(denied_request())


__all__ = []
