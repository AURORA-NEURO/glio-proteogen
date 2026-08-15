"""M06-06 lifecycle, replay, strict-ingress, and adapter parity tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from evals.m06_06.run import build_scenario
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m06_06 import (
    M0606_MAX_COMPONENTS,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition import (
    M0606Plugin,
    M0606Service,
    M0606UncertaintyDecompositionAuthorizationError,
    M0606UncertaintyDecompositionEngine,
    ValidatedM0606Request,
)

pytestmark = pytest.mark.integration

_SCHEMA_NAMES = (
    "request",
    "output",
    "component",
    "decomposition",
    "sensitivity-envelope",
    "policy",
    "finding",
)
_HTTP_OK = 200
_HTTP_UNSUPPORTED_MEDIA_TYPE = 415
_HTTP_UNPROCESSABLE_ENTITY = 422
_CLI_INVALID_REQUEST = 2


def test_schema_inventory_and_draft202012_validity() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == _SCHEMA_NAMES
    assert len(schemas) == M0606_MAX_COMPONENTS
    for name in _SCHEMA_NAMES:
        schema = contract_json_schema(name)  # type: ignore[arg-type]
        Draft202012Validator.check_schema(schema)
        assert str(schema["$id"]).endswith(f":{name}")
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True


def test_engine_abstains_when_calibration_is_not_locked() -> None:
    scenario = build_scenario()
    result = M0606Service().execute(scenario.request)
    assert result.status.value == "abstained"
    assert result.decomposition is None
    assert result.sensitivity_envelope.status is SensitivityEnvelopeStatus.ABSTAINED
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert result.result_digest.startswith("sha256:")


def test_upstream_abstention_never_becomes_negative() -> None:
    result = M0606Service().execute(build_scenario(upstream_abstained=True).request)
    assert result.status.value == "abstained"
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.findings[0].code.value == "upstream_abstained"


def test_stale_upstream_result_digest_is_rejected() -> None:
    scenario = build_scenario()
    upstream = scenario.request.constraint_result
    stale = upstream.model_construct(
        **{**upstream.__dict__, "result_digest": "sha256:" + ("b" * 64)}
    )
    request = scenario.request.model_construct(
        **{**scenario.request.__dict__, "constraint_result": stale}
    )
    with pytest.raises(ValueError, match="result digest is stale"):
        M0606UncertaintyDecompositionEngine()._result(request)


def test_stale_upstream_request_digest_is_rejected() -> None:
    scenario = build_scenario()
    upstream = scenario.request.constraint_result
    stale = upstream.model_construct(
        **{**upstream.__dict__, "request_digest": "sha256:" + ("c" * 64)}
    )
    request = scenario.request.model_construct(
        **{**scenario.request.__dict__, "constraint_result": stale}
    )
    with pytest.raises(ValueError, match="request digest is stale"):
        M0606UncertaintyDecompositionEngine()._result(request)


@pytest.mark.parametrize(
    ("role", "state"),
    [
        ("approved_configuration", UpstreamDecisionState.REJECTED),
        ("identity_lineage", IdentityLineageState.UNRESOLVED),
        ("provenance", UpstreamDecisionState.REJECTED),
        ("consent", ConsentState.WITHHELD),
        ("quality", UpstreamDecisionState.REJECTED),
        ("support", UpstreamDecisionState.REJECTED),
        ("intended_use", UpstreamDecisionState.REJECTED),
    ],
)
def test_each_control_denial_fails_before_execution(role: str, state: object) -> None:
    request = build_scenario().request
    references = request.context.references
    reference = getattr(references, role)
    changed = reference.model_copy(update={"state": state})
    request = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": references.model_copy(update={role: changed})}
            )
        }
    )
    with pytest.raises(M0606UncertaintyDecompositionAuthorizationError):
        M0606Service().execute(request)


def test_plugin_rejects_forged_and_copied_tokens() -> None:
    plugin = M0606Plugin(M0606Service())
    token = plugin.validate(build_scenario().request)
    assert plugin.run(token).status.value == "abstained"
    forged = ValidatedM0606Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    copied = ValidatedM0606Request(request=token.request, _seal=token._seal)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(copied)


def test_plugin_bytes_ingress_is_strict() -> None:
    plugin = M0606Plugin(M0606Service())
    body = canonical_json_bytes(build_scenario().request.model_dump(mode="json"))
    assert plugin.validate(body).request.request_id == "m0606.request"
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(body[:-1] + b",\"unknown\":1}")


def test_sensitivity_shape_rejects_missing_evaluated_bounds() -> None:
    with pytest.raises(ValueError, match="requires bounds"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            nominal_coverage=0.9,
            rationale="incomplete",
        )


def test_api_schema_and_result_parity(tmp_path: Path) -> None:
    scenario = build_scenario()
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        for name in _SCHEMA_NAMES:
            response = client.get(f"/v1/contracts/M06-06/{name}/schema")
            assert response.status_code == _HTTP_OK
            assert response.json() == contract_json_schema(name)  # type: ignore[arg-type]
        response = client.post(
            "/v1/modules/M06-06/decompose",
            content=canonical_json_bytes(scenario.request.model_dump(mode="json")),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == _HTTP_OK
    expected = M0606Service().execute(scenario.request).model_dump(mode="json")
    assert response.json() == expected


def test_api_rejects_wrong_media_and_duplicate_json(tmp_path: Path) -> None:
    scenario = build_scenario()
    body = canonical_json_bytes(scenario.request.model_dump(mode="json"))
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        wrong = client.post(
            "/v1/modules/M06-06/decompose",
            content=body,
            headers={"content-type": "text/plain"},
        )
        duplicate = client.post(
            "/v1/modules/M06-06/decompose",
            content=b'{"operation":"decompose_protein_abundance_uncertainty","operation":"decompose_protein_abundance_uncertainty"}',
            headers={"content-type": "application/json"},
        )
    assert wrong.status_code == _HTTP_UNSUPPORTED_MEDIA_TYPE
    assert duplicate.status_code == _HTTP_UNPROCESSABLE_ENTITY


def test_cli_schema_and_file_result_parity(tmp_path: Path) -> None:
    scenario = build_scenario()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "output.json"
    request_path.write_bytes(canonical_json_bytes(scenario.request.model_dump(mode="json")))
    runner = CliRunner()
    schema = runner.invoke(app, ["uncertainty-decomposition", "export-schema", "request"])
    result = runner.invoke(
        app,
        ["uncertainty-decomposition", "decompose", str(request_path), "--output", str(output_path)],
    )
    assert schema.exit_code == 0
    assert result.exit_code == 0, result.output
    expected = M0606Service().execute(scenario.request).model_dump(mode="json")
    assert json.loads(output_path.read_text(encoding="utf-8")) == expected


def test_cli_does_not_publish_on_invalid_request(tmp_path: Path) -> None:
    request_path = tmp_path / "bad.json"
    output_path = tmp_path / "output.json"
    request_path.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(
        app,
        ["uncertainty-decomposition", "decompose", str(request_path), "--output", str(output_path)],
    )
    assert result.exit_code == _CLI_INVALID_REQUEST
    assert not output_path.exists()
