"""Adversarial closure for M22-03 contract, replay, and interface boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m22_03.fixture import denied_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m22_03 import (
    BaselineKind,
    BaselineRun,
    BenchmarkFinding,
    BenchmarkFindingCode,
    BenchmarkStatus,
    canonical_request_digest,
    normalized_request,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import SupportDecision, SupportStatus
from glio_proteogen.modules.c21_reference_material.m22_03_internal_benchmark_ablation import (
    BenchmarkSubmission,
    M2203BenchmarkEngine,
    M2203Plugin,
    M2203ReplayError,
    M2203Service,
    cli_app,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m22_03_internal_benchmark_ablation import (
    cli as cli_module,
)
from tests.contract.test_m22_03_hardening import (
    _completed_result,
    _dossier,
    _request,
    _result_update,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_UNPROCESSABLE = 422


def test_canonical_dict_projection_and_digest_are_stable() -> None:
    request = _request()
    document = normalized_request(request)
    assert canonical_request_digest(document) == canonical_request_digest(request)
    assert result_identifier(document) == result_identifier(request)


def test_baseline_and_dossier_identity_closures_reject_duplicates() -> None:
    request = _request()
    baseline = request.baseline_runs[0]
    duplicate_metric = baseline.metrics[0]
    with pytest.raises(ValidationError, match="baseline metric ids"):
        BaselineRun.model_validate(
            baseline.model_dump(mode="python") | {"metrics": (duplicate_metric, duplicate_metric)},
            strict=True,
        )
    dossier = _dossier(request)
    with pytest.raises(ValidationError, match="dossier ids"):
        dossier.__class__.model_validate(
            dossier.model_dump(mode="python")
            | {"metrics": (dossier.metrics[0], dossier.metrics[0])},
            strict=True,
        )
    with pytest.raises(ValidationError, match="nested baseline metric ids"):
        dossier.__class__.model_validate(
            dossier.model_dump(mode="python")
            | {
                "baselines": (
                    baseline,
                    baseline.__class__.model_validate(
                        baseline.model_dump(mode="python")
                        | {"run_id": "mature-copy", "kind": BaselineKind.MATURE},
                        strict=True,
                    ),
                ),
                "comparisons": (
                    dossier.comparisons[0].model_copy(update={"candidate_run_id": "mature-copy"}),
                ),
            },
            strict=True,
        )


def test_result_replay_closure_rejects_each_identity_invariant() -> None:
    request = _request()
    result = _completed_result(request)
    with pytest.raises(ValidationError, match="request digest"):
        _result_update(result, request_digest=sha256_digest("wrong"))
    with pytest.raises(ValidationError, match="result id"):
        _result_update(result, result_id="m2203-result:wrong")
    with pytest.raises(ValidationError, match="module id"):
        _result_update(
            result,
            provenance=result.provenance.model_copy(update={"module_id": "GLIO-PROTEOGEN-M22-04"}),
        )
    with pytest.raises(ValidationError, match="upstream result digest"):
        _result_update(
            result,
            provenance=result.provenance.model_copy(
                update={"input_digests": ("sha256:" + "e" * 64,)}
            ),
        )
    finding = BenchmarkFinding(
        finding_id="duplicate",
        code=BenchmarkFindingCode.BASELINE_FAILURE,
        message="failure",
    )
    with pytest.raises(ValidationError, match="finding ids"):
        _result_update(result, findings=(finding, finding))


def test_result_replay_rejects_self_rehashed_dossier_mutation() -> None:
    request = _request()
    result = _completed_result(request)
    forged = result.model_copy(deep=True)
    assert forged.dossier is not None
    object.__setattr__(forged, "dossier", forged.dossier.model_copy(update={"comparisons": ()}))
    object.__setattr__(forged, "result_digest", result_payload_digest(forged))
    with pytest.raises(M2203ReplayError):
        M2203BenchmarkEngine().replay(forged)


def test_result_status_closure_rejects_unsafe_completed_and_abstained() -> None:
    request = _request()
    result = _completed_result(request)
    with pytest.raises(ValidationError, match="completed result"):
        _result_update(result, dossier=None)
    with pytest.raises(ValidationError, match="abstained result"):
        _result_update(
            result,
            status=BenchmarkStatus.ABSTAINED,
            dossier=None,
            abstention_reason=None,
            support_decision=SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="unsupported",
                rationale="not supported",
            ),
        )


def test_fastapi_rejects_non_object_replay_envelope() -> None:
    client = TestClient(create_app(M2203Service()))
    response = client.post("/v1/modules/M22-03/verify", content=b"[]")
    assert response.status_code == _HTTP_UNPROCESSABLE


def test_plugin_accepts_typed_submission_and_cli_prints_schema(tmp_path: Path) -> None:
    request = _request()
    plugin = M2203Plugin(M2203Service())
    validated = plugin.validate(BenchmarkSubmission(request=request))
    assert plugin.run(validated).result_digest.startswith("sha256:")
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "request"]).exit_code == 0
    denied = tmp_path / "denied.json"
    denied.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(denied)]).exit_code != 0


def test_cli_denied_and_replay_mismatch_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_path = tmp_path / "denied.json"
    request_path.write_bytes(denied_request().model_dump_json().encode())
    runner = CliRunner()
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["benchmark", str(request_path)]).exit_code != 0
    valid_path = tmp_path / "valid.json"
    valid_path.write_bytes(_completed_result(_request()).model_dump_json().encode())

    class Mismatch:
        result_digest = "sha256:" + "0" * 64

    class Service:
        def replay(self, _result: object) -> Mismatch:
            return Mismatch()

    monkeypatch.setattr(cli_module, "_SERVICE", Service())
    assert runner.invoke(cli_app, ["verify", str(valid_path)]).exit_code != 0


__all__ = []
