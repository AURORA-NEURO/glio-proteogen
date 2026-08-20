"""Adversarial runtime and interface closure for M23-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from evals.m23_03.fixture import denied_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m23_03 import (
    BaselineRun,
    BenchmarkDossier,
    ValidationStatus,
    result_payload_digest,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c21_reference_material.m23_03_internal_benchmark_ablation import (
    BenchmarkSubmission,
    M2303AuthorizationError,
    M2303Plugin,
    M2303ReplayError,
    M2303Service,
    cli_app,
    create_app,
    preflight_m2303_authorization,
    run_variant_peptide_internal_benchmark,
)
from glio_proteogen.modules.c21_reference_material.m23_03_internal_benchmark_ablation import (
    cli as cli_module,
)
from tests.contract.test_m23_03_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_UNPROCESSABLE = 422
_HTTP_OK = 200


def test_preflight_rejects_non_mapping_and_missing_context() -> None:
    with pytest.raises(M2303AuthorizationError):
        preflight_m2303_authorization(object())
    with pytest.raises(M2303AuthorizationError):
        preflight_m2303_authorization({"context": None})


def test_service_accepts_canonical_json_and_engine_public_entrypoint() -> None:
    request = _request()
    assert (
        M2303Service().validate_request(request.model_dump_json()).request_id == request.request_id
    )
    assert run_variant_peptide_internal_benchmark(request).status.value == "completed"


def test_replay_closes_request_and_identifier_identity() -> None:
    service = M2303Service()
    result = service.generate(_request())
    with pytest.raises(ValueError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "0" * 64}))
    with pytest.raises(ValueError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "wrong-result-id"}))


def test_provenance_binds_the_complete_canonical_benchmark_request() -> None:
    service = M2303Service()
    request = _request()
    result = service.generate(request)

    assert result.request_digest in result.provenance.input_digests

    metric = request.baseline_runs[0].metrics[0]
    changed_request = request.model_copy(
        update={
            "baseline_runs": (
                request.baseline_runs[0].model_copy(
                    update={"metrics": (metric.model_copy(update={"tolerance": 0.3}),)}
                ),
                *request.baseline_runs[1:],
            )
        }
    )
    changed_result = service.generate(changed_request)
    assert changed_result.request_digest != result.request_digest
    assert changed_result.provenance.input_digests[0] == changed_result.request_digest


@pytest.mark.parametrize("mutation", ["dossier", "evidence"])
def test_replay_rejects_self_rehashed_semantic_mutations(mutation: str) -> None:
    service = M2303Service()
    result = service.generate(_request())
    dossier = result.dossier
    assert dossier is not None
    if mutation == "dossier":
        forged = result.model_copy(
            update={"dossier": dossier.model_copy(update={"version": "0.1.1"})}
        )
    else:
        forged = result.model_copy(
            update={
                "evidence": (
                    result.evidence[0].model_copy(update={"claim": "forged evidence claim"}),
                )
            }
        )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(M2303ReplayError, match="replay verification"):
        service.replay(forged)


def test_contract_nested_identity_closures_reject_duplicates() -> None:
    request = _request()
    metric = request.baseline_runs[0].metrics[0]
    with pytest.raises(ValidationError, match="metric ids"):
        BaselineRun.model_validate(
            request.baseline_runs[0].model_dump(mode="python") | {"metrics": (metric, metric)},
            strict=True,
        )
    dossier = M2303Service().generate(request).dossier
    assert dossier is not None
    duplicate_run = dossier.baselines[1].model_copy(update={"run_id": dossier.baselines[0].run_id})
    with pytest.raises(ValidationError, match="dossier ids"):
        BenchmarkDossier.model_validate(
            dossier.model_dump(mode="python")
            | {"baselines": (dossier.baselines[0], duplicate_run)},
            strict=True,
        )
    duplicate_metric = dossier.baselines[1].model_copy(
        update={"metrics": (dossier.baselines[0].metrics[0],)}
    )
    with pytest.raises(ValidationError, match="nested baseline metric ids"):
        BenchmarkDossier.model_validate(
            dossier.model_dump(mode="python")
            | {"baselines": (dossier.baselines[0], duplicate_metric)},
            strict=True,
        )
    duplicate_comparison = dossier.comparisons[0].model_copy(
        update={"candidate_run_id": dossier.comparisons[0].reference_run_id}
    )
    with pytest.raises(ValidationError, match="distinct"):
        BenchmarkDossier.model_validate(
            dossier.model_dump(mode="python") | {"comparisons": (duplicate_comparison,)},
            strict=True,
        )


def test_preflight_mapping_exception_fails_closed() -> None:
    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError

    with pytest.raises(M2303AuthorizationError):
        preflight_m2303_authorization(ExplodingMapping())


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


def test_plugin_rejects_untyped_submission_and_exposes_descriptor() -> None:
    plugin = M2303Plugin(M2303Service())
    with pytest.raises(TypeError, match="validation requires"):
        plugin.validate(object())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M23-03"


def test_fastapi_verify_rejects_tampered_result_without_traceback() -> None:
    service = M2303Service()
    client = TestClient(create_app(service))
    result = service.generate(_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "0" * 64
    response = client.post("/v1/modules/M23-03/verify", json=result)
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_fastapi_known_schema_and_sanitized_auth_and_json_errors() -> None:
    client = TestClient(create_app(M2303Service()))
    assert client.get("/v1/modules/M23-03/schemas/request").status_code == _HTTP_OK
    denied_json = denied_request().model_dump_json()
    validate = client.post("/v1/modules/M23-03/validate", content=denied_json)
    benchmark = client.post("/v1/modules/M23-03/benchmark", content=denied_json)
    assert validate.status_code == benchmark.status_code == _HTTP_UNPROCESSABLE
    malformed = client.post("/v1/modules/M23-03/verify", content=b"not-json")
    assert malformed.status_code == _HTTP_UNPROCESSABLE


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


def test_typer_benchmark_emits_stdout_when_output_is_omitted(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text(_request().model_dump_json(), encoding="utf-8")
    invoked = CliRunner().invoke(cli_app, ["benchmark", str(path)])
    assert invoked.exit_code == 0
    assert json.loads(invoked.stdout)["status"] == "completed"


def test_typer_sanitizes_auth_unknown_schema_and_replay_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(denied_request().model_dump_json(), encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(denied_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["benchmark", str(denied_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(cli_app, ["export-schema", "request"]).exit_code == 0
    result_path = tmp_path / "result.json"
    result_path.write_text(M2303Service().generate(_request()).model_dump_json(), encoding="utf-8")
    invalid_path = tmp_path / "invalid-result.json"
    invalid_path.write_text("[]", encoding="utf-8")
    assert runner.invoke(cli_app, ["verify", str(invalid_path)]).exit_code != 0

    class FakeService:
        def replay(self, result: Any) -> Any:
            return result.model_copy(update={"result_digest": "sha256:" + "0" * 64})

    monkeypatch.setattr(cli_module, "_SERVICE", FakeService())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 1

    class BrokenService:
        def replay(self, result: Any) -> Any:
            del result
            raise ValueError("private replay details")  # noqa: TRY003

    monkeypatch.setattr(cli_module, "_SERVICE", BrokenService())
    failed = runner.invoke(cli_app, ["verify", str(result_path)])
    assert failed.exit_code != 0
    assert "private replay details" not in failed.output


__all__ = []
