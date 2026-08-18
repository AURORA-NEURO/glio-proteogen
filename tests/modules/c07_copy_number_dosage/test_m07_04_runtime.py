"""Adversarial runtime tests for provisional M07-04."""

from __future__ import annotations

import pytest
from evals.m07_04.run import request
from pydantic import ValidationError

from glio_proteogen.contracts.m07_04 import (
    EstimatorObservation,
    ProbabilisticEstimatorFamily,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c07_copy_number_dosage.m07_04_probabilistic_advanced_estimator import (
    M0704Plugin,
    M0704Service,
    ProbabilisticEstimatorAuthorizationError,
    ProbabilisticEstimatorInputError,
    ProbabilisticEstimatorReplayError,
    ValidatedM0704Request,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_04_probabilistic_advanced_estimator import (
    engine as m0704_engine,
)


def test_service_accepts_typed_mapping_bytes_and_string() -> None:
    service = M0704Service()
    typed = request()
    expected = service.execute(typed)
    mapping = service.execute(typed.model_dump(mode="json"))
    payload = canonical_json_bytes(typed.model_dump(mode="json"))
    assert service.execute(payload) == expected
    assert service.execute(payload.decode("utf-8")) == expected
    assert mapping == expected
    assert canonical_request_digest(typed).startswith("sha256:")


def test_service_rejects_wrong_shapes_and_duplicate_transport() -> None:
    service = M0704Service()
    with pytest.raises(ProbabilisticEstimatorInputError):
        service.execute(3)
    with pytest.raises(ProbabilisticEstimatorInputError):
        service.execute(b"[]")
    with pytest.raises(ProbabilisticEstimatorInputError):
        service.execute(b'{"context":{},"context":{}}')


def test_plain_materialization_rejects_recursive_and_oversized_values() -> None:
    nested: object = "leaf"
    for _ in range(70):
        nested = {"nested": nested}
    with pytest.raises(ValueError, match="request is invalid"):
        m0704_engine._plain_value(nested)
    with pytest.raises(ValueError, match="request is invalid"):
        m0704_engine._plain_value(["item"] * 4_097)


def test_authorization_fails_before_execution() -> None:
    with pytest.raises(ProbabilisticEstimatorAuthorizationError):
        M0704Service().execute(request(accepted_controls=False))


def test_optimizer_and_family_boundaries_abstain() -> None:
    service = M0704Service()
    wrong_optimizer = service.execute(request(optimizer="unreviewed_optimizer"))
    wrong_family = service.execute(
        request(family=ProbabilisticEstimatorFamily.VARIANT_PEPTIDE_GRAPH)
    )
    assert not wrong_optimizer.estimates
    assert not wrong_family.estimates
    assert wrong_optimizer.human_review_required
    assert wrong_family.human_review_required


def test_categorical_observation_is_explicitly_not_estimable() -> None:
    result = M0704Service().execute(request(categorical=True))
    assert result.status.value == "abstained"
    assert result.abstention_reason is not None
    assert result.diagnostics[0].status.value == "not_evaluable"


def test_plugin_token_is_single_use_capability_boundary() -> None:
    service = M0704Service()
    plugin = M0704Plugin(service)
    token = plugin.validate(request())
    assert plugin.run(token).status.value == "estimated"
    forged = ValidatedM0704Request(request=request(), _seal=object())
    with pytest.raises(TypeError):
        plugin.run(forged)


def test_plugin_rejects_duplicate_json() -> None:
    plugin = M0704Plugin(M0704Service())
    with pytest.raises(StrictJsonError):
        plugin.validate(b'{"context":{},"context":{}}')


def test_replay_without_replay_and_tamper_with_replay() -> None:
    service = M0704Service()
    result = service.execute(request())
    assert service.verify(result, replay=False) == result
    tampered_payload = result.model_dump(mode="json")
    tampered_payload["estimates"][0]["estimate_value"] = 999.0
    tampered_payload["result_digest"] = result_payload_digest(tampered_payload)
    with pytest.raises(ProbabilisticEstimatorReplayError):
        service.verify(tampered_payload)


def test_observation_shape_and_digest_boundaries() -> None:
    with pytest.raises(ValidationError):
        EstimatorObservation(
            observation_id="observation.invalid",
            feature_id="feature.invalid",
            unit="copy-number",
            source_artifact_digest="sha256:" + ("a" * 64),
        )
    invalid = request().model_dump(mode="json")
    invalid["observations"][0]["source_artifact_digest"] = "sha256:" + ("9" * 64)
    with pytest.raises(ProbabilisticEstimatorInputError):
        M0704Service().execute(invalid)
