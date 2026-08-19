"""M27-08 runtime, capability and safe-failure tests."""

# These tests assert sanitized boundary errors and capability rejection.
# ruff: noqa: PT017, TRY003

from evals.m27_08.fixture import build_request

from glio_proteogen.contracts.m27_08 import (
    M2708_MAX_CANONICAL_REQUEST_BYTES,
    RetirementRunStatus,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import (
    M2708Plugin,
    M2708RetirementEngine,
    M2708Service,
    RetirementSubmission,
)


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


def test_plugin_rejects_nested_request_mutation() -> None:
    plugin = M2708Plugin()
    token = plugin.validate(RetirementSubmission(build_request()))
    object.__setattr__(token.request, "request_id", "m2708.tampered")
    try:
        plugin.run(token)
    except ValueError as error:
        assert "capability" in str(error)
    else:
        raise AssertionError("nested request mutation must invalidate the capability")


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
