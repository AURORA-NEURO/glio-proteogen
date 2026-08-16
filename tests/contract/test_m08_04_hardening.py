"""Adversarial contract and transport coverage for M08-04."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.m08_04 import create_m0804_app, m0804_app
from glio_proteogen.contracts.m08_04 import (
    M0804_MAX_CANONICAL_REQUEST_BYTES,
    EstimatorConstraint,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticFeatureObservation,
    ProbabilisticFeatureState,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    normalized_request,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_04_probabilistic_estimator as runtime,
)
from tests.modules.c08_transcript_protein_discordance.test_m08_04_lifecycle import (
    _artifact,
    _request,
)

_HTTP_UNPROCESSABLE = 422
_HTTP_TOO_LARGE = 413
_HTTP_FORBIDDEN = 403


class _WeakObject:
    pass


class _HostileObject:
    @property
    def context(self) -> object:
        raise RuntimeError("hostile context")  # noqa: TRY003


def test_feature_and_configuration_identity_closures() -> None:
    with pytest.raises(ValidationError):
        ProbabilisticFeatureObservation(
            feature_id="feature.observed",
            state=ProbabilisticFeatureState.OBSERVED,
            unit="ratio",
            weight=1.0,
        )
    with pytest.raises(ValidationError):
        ProbabilisticFeatureObservation(
            feature_id="feature.missing",
            state=ProbabilisticFeatureState.MISSING,
            unit="ratio",
            value=0.2,
            weight=1.0,
        )
    prior = ProbabilisticPrior(
        prior_id="prior.same",
        version="1.0.0",
        kind=ProbabilisticPriorKind.NORMAL,
        parameters=(0.1,),
    )
    request = _request()
    with pytest.raises(ValidationError):
        runtime.M0804Service().validate_request(
            request.model_copy(
                update={
                    "configuration": request.configuration.model_copy(
                        update={"priors": (prior, prior)}
                    )
                }
            )
        )
    constraint = EstimatorConstraint(
        constraint_id="constraint.same",
        expression="x >= 0",
        hard=True,
    )
    with pytest.raises(ValidationError):
        runtime.M0804Service().validate_request(
            request.model_copy(
                update={
                    "configuration": request.configuration.model_copy(
                        update={"constraints": (constraint, constraint)}
                    )
                }
            )
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": PosteriorEstimateKind.SCALAR, "estimate_value": None},
        {
            "kind": PosteriorEstimateKind.INTERVAL,
            "estimate_value": 0.5,
            "lower_bound": 0.8,
            "upper_bound": 0.2,
        },
        {"kind": PosteriorEstimateKind.CATEGORICAL, "category": None},
    ],
)
def test_posterior_shapes_are_not_silently_coerced(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PosteriorEstimate(feature_id="posterior.bad", unit="probability", **kwargs)


def test_diagnostic_and_request_bindings_reject_tampering() -> None:
    with pytest.raises(ValidationError):
        OptimizationDiagnostic(
            diagnostic_id="diagnostic.failed",
            status=OptimizationDiagnosticStatus.FAILED,
            objective="objective",
            iteration_count=0,
            objective_value=0.1,
            message="failed",
        )
    request = _request()
    service = runtime.M0804Service()
    with pytest.raises(ValidationError):
        service.validate_request(request.model_copy(update={"baseline_result": _artifact("wrong")}))
    with pytest.raises(ValidationError):
        service.validate_request(
            request.model_copy(
                update={"feature_observations": (request.feature_observations[0],) * 2}
            )
        )
    with pytest.raises(ValidationError):
        service.validate_request(
            request.model_copy(
                update={"source_artifacts": (request.source_artifacts[0],) * 2}
            )
        )


def test_empty_input_abstains_and_hostile_preflight_fails_closed() -> None:
    request = _request().model_copy(update={"feature_observations": ()})
    result = runtime.M0804Service().execute(request)
    assert result.status.value == "abstained"
    with pytest.raises(PermissionError):
        runtime.M0804Service().execute(object())
    with pytest.raises(PermissionError):
        runtime.M0804Service().execute(_HostileObject())
    assert runtime.M0804ProbabilisticEstimator().validate(_request()) == _request()
    with pytest.raises(TypeError):
        runtime.M0804ProbabilisticEstimator().estimate_validated(object())  # type: ignore[arg-type]


def test_json_limits_plugin_token_and_replay_mismatch() -> None:
    request = _request()
    service = runtime.M0804Service()
    result = service.execute(request)
    with pytest.raises(ValueError, match="byte limit"):
        runtime.validate_json_request(request, b"x" * (M0804_MAX_CANONICAL_REQUEST_BYTES + 1))
    with pytest.raises(ValueError, match="does not match"):
        service.replay(request.model_copy(update={"request_id": "request.changed"}), result)
    plugin = runtime.M0804Plugin(service)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(_WeakObject())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(
            runtime.ValidatedM0804Request(request=request, _seal=object())
        )


def test_api_and_cli_error_paths(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(create_m0804_app())
    request = _request()
    invalid = request.model_dump(mode="json")
    invalid.pop("source_artifacts")
    response = client.post("/v1/modules/M08-04/probabilistic-estimate", json=invalid)
    assert response.status_code == _HTTP_UNPROCESSABLE
    oversized = client.post(
        "/v1/modules/M08-04/probabilistic-estimate",
        content=b"x" * (M0804_MAX_CANONICAL_REQUEST_BYTES + 1),
    )
    assert oversized.status_code == _HTTP_TOO_LARGE

    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    runner = CliRunner()
    validation = runner.invoke(m0804_app, ["validate", str(path)])
    assert validation.exit_code == 1
    missing = runner.invoke(m0804_app, ["validate", str(tmp_path / "missing.json")])
    assert missing.exit_code == 1


def test_byte_and_string_json_paths_are_equivalent() -> None:
    request = _request()
    payload = request.model_dump_json()
    string = runtime.validate_json_request(request.model_dump(mode="json"), payload)
    binary = runtime.validate_json_request(request.model_dump(mode="json"), payload.encode())
    assert string == binary
    assert sha256_digest(string) == sha256_digest(binary)
    assert normalized_request({"value": 1}) == {"value": 1}


def test_api_and_cli_authorization_and_parse_errors(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    withheld = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={
                            "consent": request.context.references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    invalid = request.model_dump(mode="json")
    invalid["baseline_result"]["media_type"] = "application/invalid"
    client = TestClient(create_m0804_app())
    forbidden = client.post(
        "/v1/modules/M08-04/probabilistic-estimate",
        content=withheld.model_dump_json(),
    )
    assert forbidden.status_code == _HTTP_FORBIDDEN
    malformed = client.post(
        "/v1/modules/M08-04/probabilistic-estimate",
        content=json.dumps(invalid),
    )
    assert malformed.status_code == _HTTP_UNPROCESSABLE

    path = tmp_path / "withheld.json"
    path.write_text(withheld.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    forbidden_cli = runner.invoke(m0804_app, ["estimate", str(path)])
    assert forbidden_cli.exit_code == 1
    stdin_cli = runner.invoke(m0804_app, ["validate", "-"], input=request.model_dump_json())
    assert stdin_cli.exit_code == 0
