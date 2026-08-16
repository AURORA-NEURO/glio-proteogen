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
    DecomposeProteinAbundanceUncertaintyRequest,
    ProteinAbundanceUncertaintyDecompositionResult,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
    contract_json_schema,
    contract_json_schemas,
    expected_uncertainty,
)
from glio_proteogen.contracts.m06_06.canonical import canonical_request_digest
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
    preflight_uncertainty_decomposition_authorization,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition.engine import (
    _validate_json_request,
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
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_authorization_fails_closed_for_hostile_mapping() -> None:
    class Hostile(dict[str, object]):
        def get(self, _key: str, _default: object = None) -> object:
            raise RuntimeError

    with pytest.raises(M0606UncertaintyDecompositionAuthorizationError):
        preflight_uncertainty_decomposition_authorization(
            {"context": Hostile()}
        )


def test_json_request_size_limit_runs_before_nested_validation() -> None:
    with pytest.raises(ValueError, match="byte limit"):
        _validate_json_request({}, b"x" * (4 * 1024 * 1024 + 1))


def test_validated_engine_boundary_rejects_untyped_objects() -> None:
    with pytest.raises(TypeError, match="validated request"):
        M0606UncertaintyDecompositionEngine().decompose_validated(
            cast("DecomposeProteinAbundanceUncertaintyRequest", object())
        )


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


def test_sensitivity_shape_rejects_order_and_coverage_errors() -> None:
    with pytest.raises(ValueError, match="not ordered"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            nominal_coverage=0.9,
            lower_bound=0.95,
            upper_bound=0.85,
            observed_coverage=0.9,
            rationale="inverted",
        )
    with pytest.raises(ValueError, match="85-95"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            nominal_coverage=0.9,
            lower_bound=0.8,
            upper_bound=0.95,
            observed_coverage=0.7,
            rationale="outside gate",
        )
    with pytest.raises(ValueError, match="cannot carry"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.NOT_EVALUABLE,
            nominal_coverage=0.9,
            lower_bound=0.8,
            rationale="not evaluable",
        )


def test_decomposition_requires_all_dimensions_once() -> None:
    scenario = build_scenario()
    estimate = expected_uncertainty().measurement
    component = UncertaintyComponent(
        dimension=UncertaintyDimension.MEASUREMENT,
        estimate=estimate,
        rationale="duplicate dimension test",
    )
    with pytest.raises(ValueError, match="all seven dimensions"):
        UncertaintyDecomposition(
            decomposition_id="decomposition.invalid",
            components=(component,) * 7,
            method="invalid synthetic decomposition",
            model_reference=scenario.request.source_artifacts[0],
        )


def test_valid_decomposition_and_canonical_dict_projection() -> None:
    scenario = build_scenario()
    estimate = expected_uncertainty().measurement
    decomposition = UncertaintyDecomposition(
        decomposition_id="decomposition.valid",
        components=tuple(
            UncertaintyComponent(
                dimension=dimension,
                estimate=estimate,
                rationale="synthetic valid component",
            )
            for dimension in UncertaintyDimension
        ),
        method="synthetic valid decomposition",
        model_reference=scenario.request.source_artifacts[0],
    )
    assert len(decomposition.components) == M0606_MAX_COMPONENTS
    assert canonical_request_digest(scenario.request.model_dump(mode="json")).startswith(
        "sha256:"
    )


def test_request_policy_and_result_closure_reject_tampering() -> None:
    scenario = build_scenario()
    policy = scenario.request.policy.model_construct(
        **{**scenario.request.policy.__dict__, "nominal_coverage": 0.8}
    )
    bad_request = scenario.request.model_construct(
        **{**scenario.request.__dict__, "policy": policy}
    )
    with pytest.raises(ValueError, match="nominal 90"):
        type(scenario.request).model_validate(bad_request, strict=True)

    result = M0606Service().execute(scenario.request)
    bad_request_digest = ProteinAbundanceUncertaintyDecompositionResult.model_construct(
        **{**result.__dict__, "request_digest": "sha256:" + ("d" * 64)}
    )
    with pytest.raises(ValueError, match="request digest"):
        ProteinAbundanceUncertaintyDecompositionResult.model_validate(
            bad_request_digest, strict=True
        )
    bad_result_digest = ProteinAbundanceUncertaintyDecompositionResult.model_construct(
        **{**result.__dict__, "result_digest": "sha256:" + ("e" * 64)}
    )
    with pytest.raises(ValueError, match="result digest"):
        ProteinAbundanceUncertaintyDecompositionResult.model_validate(
            bad_result_digest, strict=True
        )
    bad_status = ProteinAbundanceUncertaintyDecompositionResult.model_construct(
        **{
            **result.__dict__,
            "status": UncertaintyDecompositionStatus.DECOMPOSED,
        }
    )
    with pytest.raises(ValueError, match="decomposed result"):
        ProteinAbundanceUncertaintyDecompositionResult.model_validate(
            bad_status, strict=True
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
