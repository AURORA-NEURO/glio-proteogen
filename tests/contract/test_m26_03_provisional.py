"""Focused contract/schema smoke for provisional M26-03."""

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_03 import (
    M2603_DOSSIER_SHA256,
    M2603_DOSSIER_SLICE,
    M2603_M2601_INPUT_MEDIA_TYPE,
    M2603_M2602_INPUT_MEDIA_TYPE,
    M2603_OUTPUT_MEDIA_TYPE,
    M2603_PROVISIONAL_ABI,
    ExecutionAttempt,
    StepStatus,
    WorkflowDefinition,
    WorkflowStep,
    contract_json_schemas,
)

_SCHEMA_COUNT = 9


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", schema["x-glio-contract"])


def test_provisional_schemas_require_reproducible_execution_controls() -> None:
    schemas = cast("dict[str, dict[str, object]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(_metadata(schema)["provisionalAbi"] for schema in schemas.values())
    assert all(_metadata(schema)["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        _metadata(schema)["workflowDagRequired"]
        and _metadata(schema)["deterministicExecutionRequired"]
        and _metadata(schema)["retryAndCheckpointRequired"]
        and _metadata(schema)["environmentCaptureRequired"]
        and _metadata(schema)["reproducibilityPackageRequired"]
        and _metadata(schema)["quarantineUnresolvedInputs"]
        and _metadata(schema)["explicitAbstentionRequired"]
        and _metadata(schema)["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        _metadata(schema)["parentTarget"] == "protein subtype" for schema in schemas.values()
    )
    assert _metadata(schemas["output"])["outputMediaType"] == M2603_OUTPUT_MEDIA_TYPE
    assert M2603_PROVISIONAL_ABI is True


def test_workflow_and_attempt_invariants_are_explicit() -> None:
    with pytest.raises(ValidationError, match="unknown or self step"):
        WorkflowDefinition(
            workflow_id="workflow-1",
            version="1.0.0",
            steps=(
                WorkflowStep(
                    step_id="step-1",
                    name="deterministic step",
                    version="1.0.0",
                    dependencies=("missing-step",),
                    container_digest="sha256:" + "a" * 64,
                    resource_class="cpu-small",
                    max_retries=1,
                ),
            ),
            entry_step_ids=("step-1",),
            output_step_ids=("step-1",),
            workflow_digest="sha256:" + "b" * 64,
        )
    with pytest.raises(ValidationError, match="failed attempts require a failure reason"):
        ExecutionAttempt(
            attempt_id="attempt-1",
            step_id="step-1",
            retry_index=0,
            status=StepStatus.FAILED,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_authority_and_upstream_boundaries_are_explicit() -> None:
    assert M2603_DOSSIER_SHA256 == (
        "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M2603_DOSSIER_SLICE.endswith(":9124-9164")
    metadata = _metadata(cast("dict[str, dict[str, object]]", contract_json_schemas())["request"])
    assert metadata["mediaOnlyBoundaries"] == (
        M2603_M2601_INPUT_MEDIA_TYPE,
        M2603_M2602_INPUT_MEDIA_TYPE,
    )
