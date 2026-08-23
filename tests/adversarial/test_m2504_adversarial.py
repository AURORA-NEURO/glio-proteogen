"""Hostile-input, replay, and safe-boundary coverage for M25-04."""

from __future__ import annotations

import json
from typing import Any

import pytest
from evals.m25_04.fixture import build_request
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_04 import (
    EvaluateProteotypeExternalTransportRequest,
    ProteotypeExternalTransportResult,
    TransportStatus,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator import (
    M2504AuthorizationError,
    M2504Plugin,
    M2504ReplayError,
    M2504Service,
    TransportSubmission,
    evaluate_proteotype_external_transport,
)
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator import (
    cli as m2504_cli,
)
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator import (
    engine as m2504_engine,
)
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator.cli import (
    app,
)


def _request_data() -> dict[str, Any]:
    return build_request().model_dump(mode="python")


def test_unknown_request_field_is_rejected() -> None:
    data = _request_data()
    data["unexpected"] = "hostile"
    with pytest.raises(ValidationError):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_duplicate_evaluation_dimensions_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["evaluations"] = (request.evaluations[0], request.evaluations[0], *request.evaluations[2:])
    with pytest.raises(ValidationError, match="evaluation dimensions"):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_missing_required_dimension_is_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["evaluations"] = request.evaluations[:-1]
    with pytest.raises(ValidationError, match="every configured"):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_non_finite_transport_metric_is_rejected() -> None:
    data = _request_data()
    data["evaluations"][0]["metric_value"] = float("nan")
    with pytest.raises(ValidationError):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_wrong_benchmark_media_type_is_rejected() -> None:
    data = _request_data()
    data["benchmark_package"]["media_type"] = "application/json"
    with pytest.raises(ValidationError, match="M25-03"):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_result_digest_tampering_is_rejected() -> None:
    service = M2504Service()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})
    with pytest.raises((M2504ReplayError, ValueError)):
        service.verify_replay(tampered)


def test_result_request_digest_tampering_is_rejected() -> None:
    result = M2504Service().execute(build_request())
    tampered = result.model_copy(update={"request_digest": "sha256:" + ("f" * 64)})
    with pytest.raises(ValidationError, match="request digest"):
        ProteotypeExternalTransportResult.model_validate(tampered.model_dump(mode="python"))


def test_result_identifier_tampering_is_rejected() -> None:
    service = M2504Service()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"result_id": "result-forged"})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})
    with pytest.raises((M2504ReplayError, ValidationError)):
        service.verify_replay(tampered)


def test_result_finding_ids_are_unique() -> None:
    result = M2504Service().execute(build_request())
    assert result.findings == ()
    narrowed = M2504Service().execute(build_request(status=TransportStatus.DOMAIN_NARROWED))
    assert narrowed.findings
    duplicate = narrowed.model_copy(
        update={"findings": (narrowed.findings[0], narrowed.findings[0])}
    )
    duplicate = duplicate.model_copy(update={"result_digest": result_payload_digest(duplicate)})
    with pytest.raises(ValidationError, match="finding identifiers"):
        ProteotypeExternalTransportResult.model_validate(duplicate.model_dump(mode="python"))


def test_hostile_mapping_preflight_fails_closed() -> None:
    with pytest.raises(M2504AuthorizationError):
        M2504Service().execute({"context": {"references": {}}})


def test_preflight_bytes_plugin_and_replay_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    request = build_request()
    service = M2504Service()
    assert service.validate_request(request.model_dump_json()).request_id == request.request_id
    plugin = M2504Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M25-04"
    token = plugin.validate(TransportSubmission(request.model_dump_json().encode()))
    result = plugin.run(token)
    assert plugin.replay(result) == result
    assert plugin.validate(TransportSubmission(request)).request == request
    assert evaluate_proteotype_external_transport(request).result_digest == result.result_digest

    class BrokenContext:
        def __getattr__(self, _name: str) -> object:
            raise RuntimeError

    with pytest.raises(M2504AuthorizationError):
        M2504Service().execute({"context": BrokenContext()})

    monkeypatch.setattr(m2504_engine, "canonical_request_digest", lambda _: "sha256:" + "0" * 64)
    with pytest.raises(M2504ReplayError):
        service.verify_replay(result)
    monkeypatch.setattr(m2504_engine, "canonical_request_digest", canonical_request_digest)
    monkeypatch.setattr(m2504_engine, "result_identifier", lambda *_args: "forged")
    with pytest.raises(M2504ReplayError):
        service.verify_replay(result)
    monkeypatch.setattr(m2504_engine, "result_identifier", result_identifier)
    monkeypatch.setattr(m2504_engine, "result_payload_digest", lambda _: "sha256:" + "f" * 64)
    with pytest.raises(M2504ReplayError):
        service.verify_replay(result)


def test_duplicate_json_keys_are_rejected() -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads(b'{"request_id":"one","request_id":"two"}')


def test_plugin_requires_submission_and_validated_token() -> None:
    plugin = M2504Plugin(M2504Service())
    with pytest.raises(TypeError, match="validated request"):
        plugin.run(build_request())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="transport submission"):
        plugin.validate(build_request())


def test_plugin_rejects_duplicate_json_keys() -> None:
    plugin = M2504Plugin(M2504Service())
    with pytest.raises(StrictJsonError):
        plugin.validate(TransportSubmission(b'{"request_id":"one","request_id":"two"}'))


def test_cli_rejects_malformed_and_does_not_claim_success(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request_path = tmp_path / "bad.json"
    request_path.write_text("not-json", encoding="utf-8")
    result = CliRunner().invoke(app, ["evaluate", str(request_path)])
    assert result.exit_code != 0
    assert "ValidationError" not in result.stdout


def test_cli_verify_rejects_malformed_result(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result_path = tmp_path / "bad-result.json"
    result_path.write_text(json.dumps({"unexpected": True}), encoding="utf-8")
    result = CliRunner().invoke(app, ["verify", str(result_path)])
    assert result.exit_code != 0


def test_cli_transport_success_failure_abstention_and_replay_paths(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = build_request()
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    result = M2504Service().execute(request)
    result_path = tmp_path / "result.json"
    result_path.write_text(result.model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    assert runner.invoke(app, ["export-schema", "request"]).exit_code == 0
    assert runner.invoke(app, ["validate", str(request_path)]).exit_code == 0
    assert runner.invoke(app, ["evaluate", str(request_path)]).exit_code == 0
    output_path = tmp_path / "output.json"
    assert (
        runner.invoke(app, ["evaluate", str(request_path), "--output", str(output_path)]).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["evaluate", str(request_path), "-o", str(output_path)]).exit_code != 0
    )
    assert runner.invoke(app, ["verify", str(result_path)]).exit_code == 0

    abstained_path = tmp_path / "abstained.json"
    abstained_request = build_request(status=TransportStatus.NOT_EVALUABLE)
    abstained_path.write_text(abstained_request.model_dump_json(), encoding="utf-8")
    assert runner.invoke(app, ["evaluate", str(abstained_path)]).exit_code == 1

    class FailingService:
        def validate_request(self, _request: object) -> EvaluateProteotypeExternalTransportRequest:
            raise ValueError from None

        def execute(self, _request: object) -> ProteotypeExternalTransportResult:
            raise ValueError from None

        def verify_replay(self, _result: object) -> ProteotypeExternalTransportResult:
            raise ValueError from None

    monkeypatch.setattr(m2504_cli, "_SERVICE", FailingService())
    assert runner.invoke(app, ["validate", str(request_path)]).exit_code != 0
    assert runner.invoke(app, ["evaluate", str(request_path)]).exit_code != 0
    assert runner.invoke(app, ["verify", str(result_path)]).exit_code != 0

    class MismatchService:
        def verify_replay(self, _result: object) -> ProteotypeExternalTransportResult:
            return result.model_copy(update={"result_digest": "sha256:" + "f" * 64})

    monkeypatch.setattr(m2504_cli, "_SERVICE", MismatchService())
    mismatch = runner.invoke(app, ["verify", str(result_path)])
    assert mismatch.exit_code == 1
    assert '"verified": false' in mismatch.stdout
