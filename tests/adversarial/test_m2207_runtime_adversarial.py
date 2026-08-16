"""Deep adversarial runtime and interface-boundary cases for M22-07."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m22_07.fixture import build_request
from pydantic import ValidationError

from glio_proteogen.modules.c21_reference_material import (
    m22_07_human_factors_operational_evaluator as m2207,
)


def test_authorization_boundary_rejects_hostile_mappings_before_validation() -> None:
    with pytest.raises(m2207.M2207AuthorizationError):
        m2207.preflight_m2207_authorization({})
    with pytest.raises(ValidationError):
        m2207.M2207Service().evaluate({"context": None})


def test_strict_service_rejects_unknown_fields() -> None:
    payload = build_request().model_dump(mode="json")
    payload["unexpected"] = "must be rejected"
    with pytest.raises(ValidationError):
        m2207.M2207Service().validate_request(payload)


def test_plugin_rejects_non_object_json_and_unvalidated_execution() -> None:
    plugin = m2207.M2207Plugin(m2207.M2207Service())
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(m2207.HumanFactorsEvaluationSubmission(request=b"[]"))
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", build_request()))


def test_replay_rejects_request_mutation_even_when_result_digest_is_unchanged() -> None:
    service = m2207.M2207Service()
    result = service.evaluate(build_request())
    tampered_request = result.request.model_copy(update={"request_id": "tampered-request"})
    tampered = result.model_copy(update={"request": tampered_request})

    with pytest.raises(m2207.M2207ReplayError, match="request digest"):
        service.replay(tampered)


def test_media_boundary_drift_is_rejected_without_upstream_traversal() -> None:
    payload = build_request().model_dump(mode="json")
    payload["source_artifacts"][0]["media_type"] = "application/json"
    with pytest.raises((ValidationError, ValueError)):
        m2207.M2207Service().evaluate(payload)
