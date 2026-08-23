"""M27-08 runtime, capability and safe-failure tests."""

# ruff: noqa: PT017, TRY003

import pytest
from evals.m27_08.fixture import build_request

from glio_proteogen.contracts.m27_08 import (
    M2708_MAX_CANONICAL_REQUEST_BYTES,
    RetireComplexActivityServiceRequest,
    RetirementRunStatus,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import (
    M2708Plugin,
    M2708RetirementEngine,
    M2708Service,
    RetirementReplayError,
    RetirementSubmission,
    retire_complex_activity_service,
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


def test_inactive_dependency_identifier_is_not_an_active_substring_match() -> None:
    request = build_request()
    migration = request.migrations[0].model_copy(update={"dependency_id": "inactive-service"})
    result = M2708Service().execute(request.model_copy(update={"migrations": (migration,)}))

    assert result.status is RetirementRunStatus.EXECUTED
    assert result.package is not None


def test_preflight_rejects_empty_and_duplicate_source_artifacts() -> None:
    request = build_request()
    service = M2708Service()
    with pytest.raises(ValueError, match="at least one source"):
        service.execute(request.model_copy(update={"source_artifacts": ()}))
    with pytest.raises(ValueError, match="unique"):
        service.execute(
            request.model_copy(
                update={"source_artifacts": (request.source_artifacts[0],) * 2}
            )
        )


def test_public_retirement_function_delegates_to_engine() -> None:
    assert retire_complex_activity_service(build_request()).status is RetirementRunStatus.EXECUTED


def test_replay_wraps_execution_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M2708RetirementEngine()
    result = engine.evaluate(build_request())

    def fail(_request: RetireComplexActivityServiceRequest) -> object:
        raise RuntimeError("synthetic replay failure")

    monkeypatch.setattr(engine, "evaluate", fail)
    with pytest.raises(RetirementReplayError, match="replay failed"):
        engine.replay(result)


def test_replay_rejects_semantic_difference(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = M2708RetirementEngine()
    result = engine.evaluate(build_request())

    def different(_request: RetireComplexActivityServiceRequest) -> object:
        return result.model_copy(update={"result_id": "m2708.different"})

    monkeypatch.setattr(engine, "evaluate", different)
    with pytest.raises(RetirementReplayError, match="differs"):
        engine.replay(result)


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


def test_service_and_plugin_verify_reject_supplied_request_mismatch() -> None:
    request = build_request()
    service = M2708Service()
    result = service.execute(request)
    altered = request.model_copy(update={"request_id": "m2708.request.mismatch"})
    assert service.verify(result, altered) is False
    assert M2708Plugin().verify(result, altered) is False


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
