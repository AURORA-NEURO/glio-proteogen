"""Adversarial closure for M23-04 boundaries and failure paths."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from evals.m23_04.run import build_scenario_request
from typer.testing import CliRunner

from glio_proteogen.contracts.m23_04 import (
    EvaluateVariantPeptideExternalTransportRequest,
    SupportDomainUpdate,
    TransportConfiguration,
    TransportDimension,
    TransportStatus,
    VariantPeptideExternalTransportResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c21_reference_material.m23_04_external_transport_evaluator import (
    M2304AuthorizationError,
    M2304Engine,
    M2304Plugin,
    M2304ReplayError,
    cli_app,
    create_app,
)
from tests.contract.test_m2304_deep import _request

if TYPE_CHECKING:
    from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - optional interface dependency.
    TestClient = None  # type: ignore[assignment,misc]

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_UNCERTAINTY_FIELD_COUNT = 8


def _request_from_json(data: dict[str, Any]) -> EvaluateVariantPeptideExternalTransportRequest:
    return EvaluateVariantPeptideExternalTransportRequest.model_validate_json(
        canonical_json_bytes(data), strict=True
    )


def _data(request: EvaluateVariantPeptideExternalTransportRequest) -> dict[str, Any]:
    return request.model_dump(mode="json")


def test_duplicate_source_artifact_is_rejected() -> None:
    data = _data(_request())
    data["source_artifacts"] = [*data["source_artifacts"][:-1], data["source_artifacts"][0]]
    with pytest.raises(ValueError, match="source artifacts"):
        _request_from_json(data)


def test_source_artifact_substitution_is_rejected() -> None:
    data = _data(_request())
    replacement = dict(data["source_artifacts"][0])
    replacement["artifact_id"] = "m2304.unknown-input"
    data["source_artifacts"][-1] = replacement
    with pytest.raises(ValueError, match="source artifacts"):
        _request_from_json(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "9.9.9"),
        ("digest", "sha256:" + ("f" * 64)),
        ("media_type", "application/x-forged-transport-input"),
    ],
)
def test_declared_transport_input_metadata_must_match_source_artifact(
    field: str, value: str
) -> None:
    data = _data(_request())
    declared = dict(data["mass_spectrometry_proteome"])
    declared[field] = value
    data["mass_spectrometry_proteome"] = declared

    with pytest.raises(ValueError, match="source artifacts"):
        _request_from_json(data)


def test_duplicate_validation_and_evaluation_dimensions_are_rejected() -> None:
    data = _data(_request())
    data["configuration"]["required_dimensions"] = [
        item
        for item in data["configuration"]["required_dimensions"]
        if item != TransportDimension.SPECIMEN.value
    ]
    data["validations"][-1]["dimension"] = TransportDimension.SITE.value
    with pytest.raises(ValueError, match="validation dimensions"):
        _request_from_json(data)
    data = _data(_request())
    data["configuration"]["required_dimensions"] = [
        item
        for item in data["configuration"]["required_dimensions"]
        if item != TransportDimension.SPECIMEN.value
    ]
    data["evaluations"][-1]["dimension"] = TransportDimension.SITE.value
    with pytest.raises(ValueError, match="evaluation dimensions"):
        _request_from_json(data)


def test_context_request_id_substitution_is_rejected() -> None:
    data = _data(_request())
    data["context"]["request_id"] = "mismatched"
    with pytest.raises(ValueError, match="context"):
        _request_from_json(data)


def test_same_domain_validation_is_rejected() -> None:
    data = _data(_request())
    data["validations"][0]["target_domain"] = data["validations"][0]["source_domain"]
    with pytest.raises(ValueError, match="source and target"):
        _request_from_json(data)


def test_request_missing_configured_dimension_is_rejected() -> None:
    data = _data(_request())
    data["evaluations"] = data["evaluations"][:-1]
    with pytest.raises(ValueError, match="cover every configured"):
        _request_from_json(data)


def test_support_domain_and_configuration_closure_is_rejected() -> None:
    request = _request()
    with pytest.raises(ValueError, match="disjoint"):
        SupportDomainUpdate(
            update_id="support.invalid",
            version="0.1.0",
            status=TransportStatus.SUPPORTED,
            retained_dimensions=(TransportDimension.SITE,),
            narrowed_dimensions=(TransportDimension.SITE,),
            rationale="invalid overlap",
            evidence=(request.configuration.evidence[0],),
        )
    with pytest.raises(ValueError, match="must be unique"):
        TransportConfiguration(
            configuration_id="configuration.invalid",
            version="0.1.0",
            required_dimensions=(TransportDimension.SITE, TransportDimension.SITE),
            minimum_calibration_floor=0.8,
            evidence=(request.configuration.evidence[0],),
        )


def test_report_closure_rejects_missing_and_duplicate_dimensions() -> None:
    result = M2304Engine().evaluate(_request())
    assert result.report is not None
    report_data = result.report.model_dump(mode="json")
    report_data["validations"][0]["dimension"] = TransportDimension.LAB.value
    with pytest.raises(ValueError, match="validate every configured"):
        type(result.report).model_validate_json(canonical_json_bytes(report_data), strict=True)
    report_data = result.report.model_dump(mode="json")
    report_data["evaluations"][0]["dimension"] = TransportDimension.LAB.value
    with pytest.raises(ValueError, match="evaluate every configured"):
        type(result.report).model_validate_json(canonical_json_bytes(report_data), strict=True)
    report_data = result.report.model_dump(mode="json")
    report_data["configuration"]["required_dimensions"] = [
        item
        for item in report_data["configuration"]["required_dimensions"]
        if item != TransportDimension.SPECIMEN.value
    ]
    report_data["validations"][-1]["dimension"] = TransportDimension.SITE.value
    with pytest.raises(ValueError, match="validation dimensions"):
        type(result.report).model_validate_json(canonical_json_bytes(report_data), strict=True)
    report_data = result.report.model_dump(mode="json")
    report_data["configuration"]["required_dimensions"] = [
        item
        for item in report_data["configuration"]["required_dimensions"]
        if item != TransportDimension.SPECIMEN.value
    ]
    report_data["evaluations"][-1]["dimension"] = TransportDimension.SITE.value
    with pytest.raises(ValueError, match="evaluation dimensions"):
        type(result.report).model_validate_json(canonical_json_bytes(report_data), strict=True)
    report_data = result.report.model_dump(mode="json")
    report_data["support_domain"]["status"] = TransportStatus.SUPPORTED.value
    report_data["support_domain"]["narrowed_dimensions"] = [TransportDimension.SITE.value]
    report_data["support_domain"]["retained_dimensions"] = [
        item
        for item in report_data["support_domain"]["retained_dimensions"]
        if item != TransportDimension.SITE.value
    ]
    with pytest.raises(ValueError, match="cannot narrow"):
        type(result.report).model_validate_json(canonical_json_bytes(report_data), strict=True)


def test_result_closure_rejects_report_status_and_digest_tamper() -> None:
    result = M2304Engine().evaluate(_request())
    for field, value, message in (
        ("report", None, "supported transport report"),
        ("status", "abstained", "abstained result"),
        ("result_digest", "sha256:" + ("f" * 64), "result digest"),
    ):
        data = result.model_dump(mode="json")
        data[field] = value
        with pytest.raises(ValueError, match=message):
            VariantPeptideExternalTransportResult.model_validate_json(
                canonical_json_bytes(data), strict=True
            )


def test_canonical_projection_accepts_mapping_input() -> None:
    assert canonical_request_digest(_data(_request())).startswith("sha256:")


def test_supported_and_narrowed_metric_statuses_cannot_be_falsified() -> None:
    data = _data(_request())
    data["evaluations"][0]["status"] = TransportStatus.SUPPORTED.value
    data["evaluations"][0]["metric_value"] = 0.1
    with pytest.raises(ValueError, match="calibration floor"):
        _request_from_json(data)
    data = _data(_request())
    data["evaluations"][0]["status"] = TransportStatus.DOMAIN_NARROWED.value
    data["evaluations"][0]["metric_value"] = 0.9
    with pytest.raises(ValueError, match="calibration floor"):
        _request_from_json(data)


def test_denied_identity_and_consent_are_both_fail_closed() -> None:
    request = _request()
    identity = request.context.references.identity_lineage.model_copy(
        update={"state": "unresolved"}
    )
    references = request.context.references.model_copy(update={"identity_lineage": identity})
    context = request.context.model_copy(update={"references": references})
    with pytest.raises(M2304AuthorizationError):
        M2304Engine().evaluate(request.model_copy(update={"context": context}))


def test_hostile_mapping_cannot_bypass_preflight() -> None:
    class Hostile(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(M2304AuthorizationError):
        M2304Engine().evaluate(Hostile())


def test_strict_json_rejects_duplicate_keys_and_non_object() -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads('{"request_id":"a","request_id":"b"}')
    assert strict_json_loads("[1,2,3]") == [1, 2, 3]


def test_result_id_and_request_digest_tampering_is_rejected() -> None:
    engine = M2304Engine()
    result = engine.evaluate(_request())
    for field in ("result_id", "request_digest", "result_digest"):
        value = "sha256:" + ("f" * 64) if field != "result_id" else "transport.m2304.forged"
        with pytest.raises((ValueError, M2304ReplayError)):
            engine.replay(result.model_copy(update={field: value}))


def test_plugin_cannot_accept_a_token_from_another_instance() -> None:
    first = M2304Plugin()
    second = M2304Plugin()
    token = first.validate(_request())
    with pytest.raises(TypeError, match="validated request token"):
        second.run(token)


def test_api_unknown_schema_and_malformed_replay_are_sanitized() -> None:
    if TestClient is None:
        pytest.skip("FastAPI test client unavailable")
    client = TestClient(create_app())
    unknown = client.get("/v1/modules/M23-04/schemas/nope")
    assert unknown.status_code == _HTTP_NOT_FOUND
    malformed = client.post("/v1/modules/M23-04/verify", json={"result": {"x": 1}})
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text
    malformed_json = client.post("/v1/modules/M23-04/verify", content=b"not-json")
    assert malformed_json.status_code == _HTTP_UNPROCESSABLE
    non_object = client.post("/v1/modules/M23-04/verify", content=b"[]")
    assert non_object.status_code == _HTTP_UNPROCESSABLE
    schemas = client.get("/v1/modules/M23-04/schemas")
    assert schemas.status_code == _HTTP_OK
    invalid_validation = client.post("/v1/modules/M23-04/validate", json={"x": 1})
    assert invalid_validation.status_code == _HTTP_UNPROCESSABLE
    denied = client.post(
        "/v1/modules/M23-04/evaluate",
        json=build_scenario_request(accepted=False).model_dump(mode="json"),
    )
    assert denied.status_code == _HTTP_UNPROCESSABLE


def test_cli_abstention_returns_nonzero_and_preserves_existing_output(tmp_path: Path) -> None:
    runner = CliRunner()
    request = build_scenario_request(
        statuses=(TransportStatus.NOT_EVALUABLE,) + (TransportStatus.SUPPORTED,) * 6
    )
    source = tmp_path / "request.json"
    output = tmp_path / "result.json"
    source.write_text(request.model_dump_json())
    output.write_text("existing")
    refused = runner.invoke(cli_app, ["evaluate", str(source), "--output", str(output)])
    assert refused.exit_code != 0
    assert output.read_text() == "existing"


def test_cli_rejects_unknown_schema_and_invalid_json(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(cli_app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    source = tmp_path / "invalid.json"
    source.write_text('{"request_id":"a","request_id":"b"}')
    invalid = runner.invoke(cli_app, ["validate", str(source)])
    assert invalid.exit_code != 0
    schema_stdout = runner.invoke(cli_app, ["export-schema", "request"])
    assert schema_stdout.exit_code == 0
    denied = tmp_path / "denied.json"
    denied.write_text(build_scenario_request(accepted=False).model_dump_json())
    denied_result = runner.invoke(cli_app, ["evaluate", str(denied)])
    assert denied_result.exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}")
    verify_result = runner.invoke(cli_app, ["verify", str(bad_result)])
    assert verify_result.exit_code != 0


def test_source_media_and_all_declared_artifacts_are_preserved() -> None:
    request = build_scenario_request()
    result = M2304Engine().evaluate(request)
    observed = {artifact.artifact_id for artifact in result.request.source_artifacts}
    expected = {
        request.mass_spectrometry_proteome.artifact_id,
        request.genome_transcriptome.artifact_id,
        request.ptm_annotations.artifact_id,
        request.benchmark_package.artifact_id,
    }
    assert observed == expected
    assert result.provenance.input_digests


def test_abstention_keeps_uncertainty_and_human_review_visible() -> None:
    request = build_scenario_request(
        statuses=(TransportStatus.NOT_EVALUABLE,) + (TransportStatus.SUPPORTED,) * 6
    )
    result = M2304Engine().evaluate(request)
    assert result.report is None
    assert len(result.uncertainty.model_dump()) == _UNCERTAINTY_FIELD_COUNT
    assert result.human_review_required is True
    assert any(item.code.value == "evaluation_incomplete" for item in result.findings)
