"""M27-08 runtime, capability and safe-failure tests."""

# These tests assert sanitized boundary errors and capability rejection.
# ruff: noqa: PT017, TRY003

from http import HTTPStatus

import pytest
from evals.m27_08.fixture import build_request
from fastapi.testclient import TestClient

from glio_proteogen.contracts.m27_08 import (
    M2708_MAX_CANONICAL_REQUEST_BYTES,
    MigrationStatus,
    RetirementRunStatus,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import (
    M2708Plugin,
    M2708RetirementEngine,
    M2708Service,
    RetirementSubmission,
)
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import api as m2708_api


def test_engine_executes_complete_retirement() -> None:
    result = M2708RetirementEngine().evaluate(build_request())
    assert result.status is RetirementRunStatus.EXECUTED
    assert result.package is not None
    assert result.package.archive.status.value == "verified"


def test_incomplete_migration_abstains_with_findings() -> None:
    result = M2708Service().execute(build_request(incomplete=True))
    assert result.status is RetirementRunStatus.ABSTAINED
    assert {finding.code.value for finding in result.findings} >= {
        "criterion_unsatisfied",
        "dependency_migration_incomplete",
    }


def test_active_dependency_is_never_retired() -> None:
    result = M2708Service().execute(build_request(active_dependency=True))
    assert result.status is RetirementRunStatus.ABSTAINED
    assert any(finding.code.value == "active_dependency" for finding in result.findings)


def test_opaque_dependency_identifier_does_not_create_active_finding() -> None:
    request = build_request()
    migration = request.migrations[0].model_copy(
        update={"dependency_id": "active-looking-service"}
    )
    complete = request.model_copy(update={"migrations": (migration,)})
    result = M2708Service().execute(complete)
    assert result.status is RetirementRunStatus.EXECUTED
    assert not any(finding.code.value == "active_dependency" for finding in result.findings)


def test_in_progress_migration_is_active_even_without_marker_identifier() -> None:
    request = build_request()
    migration = request.migrations[0].model_copy(
        update={
            "dependency_id": "retired-service",
            "status": MigrationStatus.IN_PROGRESS,
        }
    )
    active = request.model_copy(update={"migrations": (migration,)})
    result = M2708Service().execute(active)
    assert result.status is RetirementRunStatus.ABSTAINED
    assert any(finding.code.value == "active_dependency" for finding in result.findings)


def test_consent_withheld_fails_before_package() -> None:
    try:
        M2708Service().execute(build_request(consent=ConsentState.WITHHELD))
    except ValueError as error:
        assert "consent" in str(error)
    else:
        raise AssertionError("withheld consent must fail closed")


def test_plugin_token_is_identity_bound() -> None:
    plugin = M2708Plugin()
    token = plugin.validate(RetirementSubmission(build_request()))
    assert plugin.run(token).status is RetirementRunStatus.EXECUTED


def test_plugin_rejects_reconstructed_token() -> None:
    plugin = M2708Plugin()
    token = plugin.validate(RetirementSubmission(build_request()))
    copied = type(token)(request=token.request, request_digest=token.request_digest)
    try:
        plugin.run(copied)
    except ValueError as error:
        assert "capability" in str(error)
    else:
        raise AssertionError("reconstructed capability must be rejected")


def test_json_execute_is_deterministic() -> None:
    service = M2708Service()
    request = build_request()
    first = service.execute_json(request.model_dump_json())
    second = service.execute_json(request.model_dump_json())
    assert first.result_digest == second.result_digest


def test_service_rejects_oversized_bytes() -> None:
    try:
        M2708Service().validate_request(b"x" * (M2708_MAX_CANONICAL_REQUEST_BYTES + 1))
    except ValueError as error:
        assert "validation failed" in str(error)
    else:
        raise AssertionError("oversized request must be rejected")


def test_service_rejects_oversized_mapping_after_json_reencoding() -> None:
    payload = build_request().model_dump(mode="json")
    payload["context"]["actor_id"] = "a" * M2708_MAX_CANONICAL_REQUEST_BYTES
    try:
        M2708Service().validate_request(payload)
    except ValueError as error:
        assert "validation failed" in str(error)
    else:
        raise AssertionError("oversized mapping must be rejected")


def test_api_applies_request_and_result_byte_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m2708_api, "M2708_MAX_CANONICAL_REQUEST_BYTES", 1)
    monkeypatch.setattr(m2708_api, "M2708_MAX_CANONICAL_RESULT_BYTES", 1)
    client = TestClient(m2708_api.create_app())
    assert (
        client.post("/v1/modules/M27-08/validate", content=b"").status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    assert (
        client.post("/v1/modules/M27-08/verify", content=b"").status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
