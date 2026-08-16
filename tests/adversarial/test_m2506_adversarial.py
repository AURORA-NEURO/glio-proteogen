"""Hostile-container and boundary closure for M25-06."""

from __future__ import annotations

import json
from typing import Any

import pytest
from evals.m25_06.fixture import build_request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m25_06 import (
    ChallengeDisposition,
    ChallengeProteotypeRobustnessRequest,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c21_reference_material.m25_06_robustness_shift_ood_challenge import (
    M2506AuthorizationError,
    M2506ReplayError,
    M2506RobustnessEngine,
    preflight_m2506_authorization,
)

_REQUEST_ADAPTER = TypeAdapter(ChallengeProteotypeRobustnessRequest)


class _ExplodingMapping(dict[str, object]):
    def get(self, key: str, default: object = None) -> object:
        del key, default
        raise RuntimeError("hostile mapping")  # noqa: TRY003


def test_hostile_mapping_fails_closed_before_access() -> None:
    with pytest.raises(M2506AuthorizationError):
        preflight_m2506_authorization(_ExplodingMapping())


def test_duplicate_json_object_members_are_rejected() -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads('{"request_id":"a","request_id":"b"}')


def test_unknown_contract_fields_are_rejected() -> None:
    payload = build_request().model_dump(mode="json")
    payload["untrusted_field"] = "must not pass"
    with pytest.raises(ValidationError):
        _REQUEST_ADAPTER.validate_json(json.dumps(payload), strict=True)


def test_wrong_upstream_media_type_is_rejected() -> None:
    payload = build_request().model_dump(mode="json")
    payload["upstream_result"]["media_type"] = "application/vnd.glio-proteogen.m25-05+json"
    with pytest.raises(ValidationError):
        _REQUEST_ADAPTER.validate_json(json.dumps(payload), strict=True)


def test_upstream_must_be_listed_in_source_artifacts() -> None:
    payload = build_request().model_dump(mode="json")
    payload["source_artifacts"] = []
    with pytest.raises(ValidationError):
        _REQUEST_ADAPTER.validate_json(json.dumps(payload), strict=True)


def test_configuration_must_cover_each_challenge_kind() -> None:
    payload = build_request().model_dump(mode="json")
    payload["configuration"]["required_challenge_kinds"] = ["missing_data"]
    with pytest.raises(ValidationError):
        _REQUEST_ADAPTER.validate_json(json.dumps(payload), strict=True)


def test_tampering_nested_surface_observation_fails_replay() -> None:
    result = M2506RobustnessEngine().challenge(build_request())
    payload: dict[str, Any] = result.model_dump(mode="python")
    assert payload["robustness_surface"] is not None
    payload["robustness_surface"]["observations"][0]["ood_score"] = 0.99
    with pytest.raises(M2506ReplayError):
        M2506RobustnessEngine().replay(payload)  # type: ignore[arg-type]


def test_safe_abstention_does_not_emit_parent_or_surface() -> None:
    result = M2506RobustnessEngine().challenge(
        build_request(disposition=ChallengeDisposition.ABSTAIN_UNSUPPORTED)
    )
    assert result.robustness_surface is None
    assert result.emits_parent is False
    assert result.safe_failure_report is not None
