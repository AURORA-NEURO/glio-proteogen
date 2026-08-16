"""Runtime, replay, service, and plugin tests for M26-03."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m26_03.fixture import build_request, denied_request

from glio_proteogen.contracts.m26_03 import (
    ExecutionStatus,
    StepStatus,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material.m26_03_reproducible_pipeline_orchestrator import (  # noqa: E501
    M2603AuthorizationError,
    M2603Engine,
    M2603EvaluationError,
    M2603Plugin,
    M2603ReplayError,
    M2603Service,
    ValidatedM2603Request,
    execute_protein_subtype_workflow,
)


def test_nominal_workflow_is_complete_and_replayable() -> None:
    request = build_request()
    result = M2603Engine().execute(request)
    assert result.status is ExecutionStatus.COMPLETED
    assert result.execution_record is not None
    assert result.reproducible_package is not None
    assert result.execution_record.execution_status is ExecutionStatus.COMPLETED
    assert all(item.status is StepStatus.COMPLETED for item in result.execution_record.attempts)
    assert result.reproducible_package.execution_id == result.execution_record.execution_id
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.parent_target == "protein subtype"
    assert result.emits_parent is False
    assert result.human_review_required is True
    assert result.request_digest == canonical_request_digest(request)
    assert M2603Engine().verify(result).result_digest == result.result_digest


@pytest.mark.parametrize(
    "field",
    [
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    ],
)
def test_denied_control_fails_before_workflow_traversal(field: str) -> None:
    request = build_request()
    decision = getattr(request.context.references, field)
    denied_state = (
        IdentityLineageState.UNRESOLVED
        if field == "identity_lineage"
        else UpstreamDecisionState.REJECTED
    )
    denied = decision.model_copy(update={"state": denied_state})
    references = request.context.references.model_copy(update={field: denied})
    candidate = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    with pytest.raises(M2603AuthorizationError):
        M2603Engine().execute(candidate)


def test_denied_fixture_and_malformed_request_are_safe_failures() -> None:
    with pytest.raises(M2603AuthorizationError):
        M2603Engine().execute(denied_request())
    with pytest.raises(M2603AuthorizationError):
        M2603Engine().execute({"request_id": "invalid"})


def test_service_and_plugin_share_strict_parse_once_boundary() -> None:
    request = build_request()
    service = M2603Service()
    validated = service.validate_request(request)
    result = service.execute(validated)
    assert service.verify(result).result_id == result.result_id
    plugin = M2603Plugin(service)
    token = plugin.validate(request.model_dump_json())
    assert isinstance(token, ValidatedM2603Request)
    plugin_result = plugin.run(token)
    assert plugin_result.result_digest == result.result_digest
    assert plugin.verify(plugin_result.model_dump_json()).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M26-03"
    assert plugin.descriptor().owner == "ML engineering"
    with pytest.raises(TypeError):
        plugin.run(cast("Any", request))
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(object())


def test_service_accepts_mapping_and_canonical_json() -> None:
    request = build_request()
    service = M2603Service()
    encoded = canonical_json_bytes(request.model_dump(mode="json"))
    from_mapping = service.execute(request.model_dump(mode="json"))
    from_json = service.execute(encoded)
    assert from_mapping == from_json
    assert service.verify(from_json.model_dump(mode="json")) == from_json
    assert service.verify(from_json.model_dump_json()) == from_json


def test_replay_rejects_payload_request_and_digest_tampering() -> None:
    engine = M2603Engine()
    result = engine.execute(build_request())
    with pytest.raises(M2603ReplayError):
        engine.verify(result.model_copy(update={"human_review_required": False}), replay=False)
    changed = build_request().model_copy(update={"request_id": "m2603-changed-request"})
    with pytest.raises(M2603ReplayError):
        engine.verify(result.model_copy(update={"request": changed}), replay=False)
    with pytest.raises(M2603ReplayError):
        engine.verify(
            result.model_copy(update={"result_digest": sha256_digest("tampered")}),
            replay=False,
        )


def test_public_function_and_invalid_result_are_closed() -> None:
    result = execute_protein_subtype_workflow(build_request())
    assert result.status is ExecutionStatus.COMPLETED
    with pytest.raises(M2603ReplayError):
        M2603Engine().verify({"result_id": "invalid"})
    invalid = build_request().model_dump(mode="python")
    invalid.pop("environment")
    with pytest.raises(M2603EvaluationError):
        M2603Engine().execute(invalid)
