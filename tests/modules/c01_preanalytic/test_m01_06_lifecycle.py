"""Focused M01-06 service and plugin lifecycle tests."""

from __future__ import annotations

from typing import cast

import pytest

from glio_proteogen.contracts.m01_06 import HarmonizationDisposition
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization import (
    HarmonizationAuthorizationError,
    M0106Plugin,
    M0106Service,
    ValidatedM0106Request,
    preflight_harmonization_authorization,
)
from tests.modules.c01_preanalytic.test_m01_06_engine import _request


def test_service_revalidates_and_executes() -> None:
    result = M0106Service().execute(_request())

    assert result.disposition is HarmonizationDisposition.ACCEPTED


def test_plugin_validates_json_then_runs() -> None:
    plugin = M0106Plugin(M0106Service())

    token = plugin.validate(_request().model_dump_json())
    result = plugin.run(token)

    assert isinstance(token, ValidatedM0106Request)
    assert result.disposition is HarmonizationDisposition.ACCEPTED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M01-06"


def test_plugin_rejects_unvalidated_execution_token() -> None:
    plugin = M0106Plugin(M0106Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM0106Request", object()))


def test_raw_preflight_rejects_before_observation_access() -> None:
    unauthorized = {
        "context": {
            "references": {
                "approved_configuration": {"state": "accepted"},
                "identity_lineage": {"state": "resolved"},
                "provenance": {"state": "accepted"},
                "consent": {"state": "revoked"},
                "quality": {"state": "accepted"},
                "support": {"state": "accepted"},
                "intended_use": {"state": "accepted"},
            }
        },
        "observations": object(),
    }

    with pytest.raises(HarmonizationAuthorizationError, match="accepted upstream authorization"):
        preflight_harmonization_authorization(unauthorized)


def test_plugin_rejects_unauthorized_raw_mapping_before_typed_validation() -> None:
    payload = _request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "revoked"
    payload["observations"] = "not-read-by-preflight"

    with pytest.raises(HarmonizationAuthorizationError, match="accepted upstream authorization"):
        M0106Plugin(M0106Service()).validate(payload)
