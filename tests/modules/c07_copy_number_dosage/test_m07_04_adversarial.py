"""Additional adversarial branch coverage for M07-04's strict boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from http import HTTPStatus

import pytest
from evals.m07_04.run import request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.m0704 import create_m0704_app, m0704_app
from glio_proteogen.contracts.m07_04 import (
    EstimatorObservation,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    canonical_result_digest,
    verify_result_digest,
)
from glio_proteogen.contracts.m07_04.v1 import (
    ProbabilisticEstimatorConfiguration,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.modules.c07_copy_number_dosage.m07_04_probabilistic_advanced_estimator import (
    M0704Plugin,
    M0704Service,
    ProbabilisticEstimatorAuthorizationError,
    ProbabilisticEstimatorInputError,
    ProbabilisticEstimatorReplayError,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_04_probabilistic_advanced_estimator import (
    engine as _m0704_engine,
)

_plain_value = _m0704_engine._plain_value
_posterior = _m0704_engine._posterior
_validate_json_request = _m0704_engine._validate_json_request
estimate_copy_number_dosage_probabilistic = _m0704_engine.estimate_copy_number_dosage_probabilistic
preflight_probabilistic_estimator_authorization = (
    _m0704_engine.preflight_probabilistic_estimator_authorization
)


class _ExampleEnum(StrEnum):
    VALUE = "value"


_CLI_CONTRACT_ERROR = 2
_CLI_REPLAY_ERROR = 4


def test_canonical_digest_rejects_unknown_and_missing_reported_values() -> None:
    result = M0704Service().execute(request())
    assert verify_result_digest(result)
    assert verify_result_digest(result.model_dump(mode="json"))
    assert not verify_result_digest({})
    assert not verify_result_digest({"result_digest": 4})
    assert not verify_result_digest(object())
    assert canonical_result_digest(result) == result.result_digest


def test_plain_value_handles_json_scalars_and_rejects_unknown_objects() -> None:
    assert _plain_value(request())
    assert _plain_value(_ExampleEnum.VALUE) == "value"
    assert _plain_value(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00+00:00"
    assert _plain_value(date(2026, 1, 1)) == "2026-01-01"
    assert _plain_value([1, "a"]) == [1, "a"]
    assert _plain_value((1, "a")) == (1, "a")
    assert _plain_value({"a": [1]}) == {"a": [1]}
    with pytest.raises(ProbabilisticEstimatorInputError):
        _plain_value({1: "not-a-string-key"})
    with pytest.raises(ProbabilisticEstimatorInputError):
        _plain_value(object())


def test_authorization_malformed_objects_fail_closed() -> None:
    for candidate in (None, "text", 5, {}, {"context": None}):
        with pytest.raises(ProbabilisticEstimatorAuthorizationError):
            preflight_probabilistic_estimator_authorization(candidate)

    class BadMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(ProbabilisticEstimatorAuthorizationError):
        preflight_probabilistic_estimator_authorization(BadMapping())


def test_plugin_descriptor_and_service_alias() -> None:
    service = M0704Service()
    plugin = M0704Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M07-04"
    assert service.estimate(request()) == service.execute(request())


def test_observation_and_posterior_shapes_are_closed() -> None:
    digest = "sha256:" + ("a" * 64)
    with pytest.raises(ValidationError):
        EstimatorObservation(
            observation_id="observation.mixed",
            feature_id="feature.mixed",
            unit="copy-number",
            source_artifact_digest=digest,
            scalar_value=1.0,
            category="amplified",
        )
    nan_observation = EstimatorObservation.model_construct(
        observation_id="observation.nan",
        feature_id="feature.nan",
        unit="copy-number",
        source_artifact_digest=digest,
        scalar_value=float("nan"),
    )
    assert _posterior(nan_observation) is None
    huge_interval = EstimatorObservation.model_construct(
        observation_id="observation.huge",
        feature_id="feature.huge",
        unit="copy-number",
        source_artifact_digest=digest,
        interval_lower=1e308,
        interval_upper=1e308,
    )
    assert _posterior(huge_interval) is None
    assert PosteriorEstimate(
        feature_id="feature.category",
        kind=PosteriorEstimateKind.CATEGORICAL,
        unit="copy-number",
        category="amplified",
    ).category == "amplified"
    with pytest.raises(ValidationError):
        EstimatorObservation(
            observation_id="observation.reversed",
            feature_id="feature.reversed",
            unit="copy-number",
            source_artifact_digest=digest,
            interval_lower=2.0,
            interval_upper=1.0,
        )
    with pytest.raises(ValidationError):
        PosteriorEstimate(
            feature_id="feature.bad",
            kind=PosteriorEstimateKind.SCALAR,
            unit="copy-number",
        )
    with pytest.raises(ValidationError):
        PosteriorEstimate(
            feature_id="feature.bad",
            kind=PosteriorEstimateKind.INTERVAL,
            unit="copy-number",
            estimate_value=4.0,
            lower_bound=1.0,
            upper_bound=2.0,
        )
    with pytest.raises(ValidationError):
        PosteriorEstimate(
            feature_id="feature.bad",
            kind=PosteriorEstimateKind.CATEGORICAL,
            unit="copy-number",
            estimate_value=1.0,
        )


def test_duplicate_configuration_and_result_diagnostics_are_rejected() -> None:
    first = ProbabilisticPrior(
        prior_id="prior.duplicate",
        version="1.0.0",
        kind=ProbabilisticPriorKind.NORMAL,
        parameters=(0.0, 1.0),
    )
    with pytest.raises(ValidationError):
        ProbabilisticEstimatorConfiguration(
            configuration_id="configuration.duplicate",
            version="1.0.0",
            estimator_family="mechanism_guided",
            representation_media_type="application/vnd.glio-proteogen.m07-02+json",
            objective="objective",
            priors=(first, first),
            optimizer="optimizer",
            seed=1,
            max_iterations=1,
            reference=ArtifactReference(
                artifact_id="representation.duplicate",
                version="1.0.0",
                digest="sha256:" + ("b" * 64),
                media_type="application/vnd.glio-proteogen.m07-02+json",
            ),
        )
    result = M0704Service().execute(request())
    payload = result.model_dump(mode="json")
    payload["diagnostics"].append(payload["diagnostics"][0])
    with pytest.raises(ValidationError):
        type(result).model_validate(payload, strict=True)


def test_request_binding_invariants_are_revalidated() -> None:
    payload = request().model_dump(mode="json")
    payload["context"]["request_id"] = "request.other"
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0704Service().execute(payload)

    payload = request().model_dump(mode="json")
    payload["configuration"]["representation_media_type"] = "application/json"
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0704Service().execute(payload)
    payload = request().model_dump(mode="json")
    payload["configuration"]["reference"]["digest"] = "sha256:" + ("9" * 64)
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0704Service().execute(payload)

    valid = request().model_dump(mode="json")
    valid["padding"] = "x" * (4 * 1024 * 1024)
    with pytest.raises(ProbabilisticEstimatorInputError):
        _validate_json_request(valid, canonical_json_bytes(valid))
    with pytest.raises(ProbabilisticEstimatorInputError):
        _validate_json_request([], b"[]")

    malformed = request()
    # Keep nested Pydantic models intact so the intentionally malformed field
    # exercises request revalidation without serializer warnings.
    object.__setattr__(malformed, "observations", ())
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0704Service().execute(malformed)

    mapping_with_non_string_key = request().model_dump(mode="json")
    mapping_with_non_string_key[1] = "bad"
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0704Service().execute(mapping_with_non_string_key)
    denied_bytes = canonical_json_bytes(request(accepted_controls=False).model_dump(mode="json"))
    with pytest.raises(ProbabilisticEstimatorAuthorizationError):
        M0704Service().execute(denied_bytes)
    payload = request().model_dump(mode="json")
    payload["observations"].append(payload["observations"][0])
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0704Service().execute(payload)
    payload = request().model_dump(mode="json")
    payload["source_artifacts"].append(payload["source_artifacts"][0])
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0704Service().execute(payload)


def test_api_authorization_mapping_and_cli_single_schema_and_verify_error(tmp_path) -> None:
    class AuthorizationFailureService:
        def execute(self, _request: object) -> object:
            raise ProbabilisticEstimatorAuthorizationError

        def verify(self, _result: object, *, replay: bool = True) -> object:
            del replay
            raise AssertionError("verify should not be called")  # noqa: TRY003

    denied_client = TestClient(create_m0704_app(AuthorizationFailureService))
    denied = denied_client.post(
        "/v1/m07-04/probabilistic/estimate",
        json=request().model_dump(mode="json"),
    )
    assert denied.status_code == HTTPStatus.FORBIDDEN

    runner = CliRunner()
    single = runner.invoke(m0704_app, ["export-schema", "request"])
    assert single.exit_code == 0
    result = M0704Service().execute(request()).model_dump(mode="json")
    tampered = tmp_path / "tampered.json"
    result["estimates"][0]["estimate_value"] = 999.0
    result["result_digest"] = canonical_result_digest(result)
    tampered.write_bytes(canonical_json_bytes(result))
    failed = runner.invoke(m0704_app, ["verify", str(tampered)])
    assert failed.exit_code == _CLI_REPLAY_ERROR
    invalid = tmp_path / "invalid-result.json"
    invalid.write_text("{}", encoding="utf-8")
    invalid_result = runner.invoke(m0704_app, ["verify", str(invalid)])
    assert invalid_result.exit_code == _CLI_CONTRACT_ERROR

    bad_digest = tmp_path / "bad-digest.json"
    digest_result = M0704Service().execute(request()).model_dump(mode="json")
    digest_result["result_digest"] = "sha256:" + ("0" * 64)
    bad_digest.write_bytes(canonical_json_bytes(digest_result))
    with pytest.raises(ProbabilisticEstimatorReplayError):
        M0704Service().verify(digest_result, replay=False)


def test_result_envelope_closure_and_top_level_function() -> None:
    result = estimate_copy_number_dosage_probabilistic(request())
    base = result.model_dump(mode="json")
    mutations = [
        {"request_digest": "sha256:" + ("0" * 64)},
        {"result_id": "result.other"},
        {"evidence": []},
        {"estimates": [base["estimates"][0], base["estimates"][0]]},
        {"diagnostics": [base["diagnostics"][0], base["diagnostics"][0]]},
        {"support_decision": {**base["support_decision"], "status": "review_required"}},
    ]
    for mutation in mutations:
        candidate = {**base, **mutation}
        with pytest.raises(ValidationError):
            type(result).model_validate(candidate, strict=True)
