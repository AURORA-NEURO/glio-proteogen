"""Adversarial runtime and interface closure for M23-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m23_03 import ValidationStatus
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c21_reference_material.m23_03_internal_benchmark_ablation import (
    BenchmarkSubmission,
    M2303AuthorizationError,
    M2303Plugin,
    M2303Service,
    cli_app,
    create_app,
    preflight_m2303_authorization,
)
from tests.contract.test_m23_03_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_UNPROCESSABLE = 422


def test_preflight_rejects_non_mapping_and_missing_context() -> None:
    with pytest.raises(M2303AuthorizationError):
        preflight_m2303_authorization(object())
    with pytest.raises(M2303AuthorizationError):
        preflight_m2303_authorization({"context": None})


def test_not_evaluable_ablation_and_comparison_are_safe_abstentions() -> None:
    request = _request()
    ablation = request.ablations[0].model_copy(update={"status": ValidationStatus.NOT_EVALUABLE})
    changed = request.model_copy(update={"ablations": (ablation,)})
    result = M2303Service().generate(changed)
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    comparison = request.comparisons[0].model_copy(
        update={"status": ValidationStatus.NOT_EVALUABLE}
    )
    changed = request.model_copy(update={"comparisons": (comparison,)})
    result = M2303Service().generate(changed)
    assert result.dossier is None
    assert result.human_review_required


def test_failed_ablation_and_comparison_remain_visible() -> None:
    request = _request()
    ablation = request.ablations[0].model_copy(update={"status": ValidationStatus.FAIL})
    comparison = request.comparisons[0].model_copy(update={"status": ValidationStatus.FAIL})
    result = M2303Service().generate(
        request.model_copy(update={"ablations": (ablation,), "comparisons": (comparison,)})
    )
    assert result.dossier is not None
    assert {finding.code.value for finding in result.findings} == {
        "ablation_failure",
        "compute_mismatch",
    }


def test_plugin_json_path_is_strict_and_replays() -> None:
    plugin = M2303Plugin(M2303Service())
    token = plugin.validate(BenchmarkSubmission(request=_request().model_dump_json()))
    result = plugin.run(token)
    assert plugin.replay(result).result_digest == result.result_digest
    with pytest.raises((ValidationError, M2303AuthorizationError)):
        plugin.validate(BenchmarkSubmission(request=b'{"request_id":null}'))


def test_fastapi_verify_rejects_tampered_result_without_traceback() -> None:
    service = M2303Service()
    client = TestClient(create_app(service))
    result = service.generate(_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "0" * 64
    response = client.post("/v1/modules/M23-03/verify", json=result)
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_typer_abstention_writes_result_and_returns_nonzero(tmp_path: Path) -> None:
    # Exercise the CLI's safe-abstention exit after the immutable result is written.
    path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request = _request()
    metric = (
        request.baseline_runs[0]
        .metrics[0]
        .model_copy(update={"status": ValidationStatus.NOT_EVALUABLE})
    )
    abstaining = request.model_copy(
        update={
            "baseline_runs": (
                request.baseline_runs[0].model_copy(update={"metrics": (metric,)}),
                *request.baseline_runs[1:],
            )
        }
    )
    path.write_text(abstaining.model_dump_json(), encoding="utf-8")
    invoked = CliRunner().invoke(cli_app, ["benchmark", str(path), "--output", str(result_path)])
    assert invoked.exit_code == 1
    assert result_path.exists()
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "abstained"


__all__ = []
