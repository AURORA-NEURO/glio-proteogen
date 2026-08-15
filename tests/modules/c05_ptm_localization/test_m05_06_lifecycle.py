"""Lifecycle, replay, sealing, and safe-failure checks for M05-06."""

from __future__ import annotations

import json

import pytest
from evals.m05_05.run import canonical_smoke
from evals.m05_06.run import build_scenario

from glio_proteogen.contracts.m05_06 import (
    M0506_MAX_CANONICAL_REQUEST_BYTES,
    M0506_OPERATION,
    M0506_PROVISIONAL_ABI,
    contract_json_schemas,
    opaque_harmonization_identifier,
)
from glio_proteogen.contracts.m05_06.canonical import canonical_request_digest
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization import (
    M0506Plugin,
    M0506Service,
    preflight_ptm_localization_harmonization_authorization,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.engine import (
    PtmLocalizationHarmonizationAuthorizationError,
    artifact_harmonization_receipt,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.plugin import (
    ValidatedM0506Request,
)

_EXPECTED_SCHEMA_COUNT = 14


def test_schema_abi_is_explicit_and_provisional() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _EXPECTED_SCHEMA_COUNT
    assert all(
        schema["x-glio-contract"]["provisionalAbi"] is True for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["pendingOwnerConfirmation"] is True
        for schema in schemas.values()
    )
    assert M0506_PROVISIONAL_ABI is True


def test_missing_request_fails_closed_at_service_boundary() -> None:
    with pytest.raises(PtmLocalizationHarmonizationAuthorizationError):
        M0506Service.validate_request({})


def test_missing_request_fails_closed_at_plugin_boundary() -> None:
    with pytest.raises(PtmLocalizationHarmonizationAuthorizationError):
        M0506Plugin(M0506Service()).validate({})


def test_authorization_preflight_rejects_hostile_candidate() -> None:
    with pytest.raises(PtmLocalizationHarmonizationAuthorizationError):
        preflight_ptm_localization_harmonization_authorization({"context": object()})


def test_authorization_preflight_rejects_each_missing_control() -> None:
    for role in (
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    ):
        references = {
            name: {"state": "accepted"}
            for name in (
                "approved_configuration",
                "identity_lineage",
                "provenance",
                "consent",
                "quality",
                "support",
                "intended_use",
            )
        }
        references["identity_lineage"]["state"] = "resolved"
        references["consent"]["state"] = "granted"
        references[role]["state"] = "rejected"
        with pytest.raises(PtmLocalizationHarmonizationAuthorizationError):
            preflight_ptm_localization_harmonization_authorization(
                {"context": {"references": references}}
            )


def test_opaque_identifier_rejects_unknown_namespace() -> None:
    with pytest.raises(ValueError, match="unknown M05-06"):
        opaque_harmonization_identifier("unknown", {"x": 1})


def test_opaque_identifier_is_deterministic_and_content_bound() -> None:
    first = opaque_harmonization_identifier("request", {"x": 1})
    second = opaque_harmonization_identifier("request", {"x": 1})
    changed = opaque_harmonization_identifier("request", {"x": 2})
    assert first == second
    assert first != changed


def test_canonical_request_digest_changes_on_mutation() -> None:
    scenario = build_scenario("clear")
    request = scenario.request
    assert canonical_request_digest(request) != canonical_request_digest(
        request.model_copy(update={"operation": M0506_OPERATION + "-tampered"})
    )


def test_artifact_receipt_replay_rejects_missing_upstream() -> None:
    with pytest.raises((AttributeError, TypeError, ValueError)):
        artifact_harmonization_receipt({})


def test_plugin_rejects_forged_token() -> None:
    plugin = M0506Plugin(M0506Service())
    forged = object.__new__(ValidatedM0506Request)
    with pytest.raises(TypeError):
        plugin.run(forged)


def test_plugin_rejects_copied_token_without_issued_registry_entry() -> None:
    plugin = M0506Plugin(M0506Service())
    token = plugin.validate(build_scenario("clear").request)
    copied = ValidatedM0506Request(request=token.request, _seal=object())
    with pytest.raises(TypeError):
        plugin.run(copied)


def test_plugin_rejects_duplicate_json_keys() -> None:
    plugin = M0506Plugin(M0506Service())
    duplicate = '{"operation":"x","operation":"y"}'
    with pytest.raises(StrictJsonError):
        plugin.validate(duplicate)


def test_plugin_rejects_oversized_json_before_deep_validation() -> None:
    plugin = M0506Plugin(M0506Service())
    oversized = json.dumps({"payload": "x" * M0506_MAX_CANONICAL_REQUEST_BYTES})
    with pytest.raises(StrictJsonError):
        plugin.validate(oversized)


def test_clear_upstream_result_is_not_silently_downgraded() -> None:
    result = canonical_smoke("clear")
    harmonized = build_scenario("clear").request.artifact_result
    assert result.disposition.value == "cleared"
    assert harmonized.disposition.value == "cleared"


def test_descriptor_and_operation_are_stable() -> None:
    descriptor = M0506Plugin(M0506Service()).descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M05-06"
    assert descriptor.version == "1.0.0-provisional"
    assert descriptor.gate == "G1"
