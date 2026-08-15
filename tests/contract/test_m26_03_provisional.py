"""Focused contract/schema smoke for provisional M26-03."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_03 import (
    M2603_OUTPUT_MEDIA_TYPE,
    M2603_PROVISIONAL_ABI,
    ExecutionAttempt,
    StepStatus,
    WorkflowDefinition,
    WorkflowStep,
    contract_json_schemas,
)

_SCHEMA_COUNT = 9


def test_provisional_schemas_require_reproducible_execution_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["workflowDagRequired"]
        and schema["x-glio-contract"]["deterministicExecutionRequired"]
        and schema["x-glio-contract"]["retryAndCheckpointRequired"]
        and schema["x-glio-contract"]["environmentCaptureRequired"]
        and schema["x-glio-contract"]["reproducibilityPackageRequired"]
        and schema["x-glio-contract"]["quarantineUnresolvedInputs"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2603_OUTPUT_MEDIA_TYPE
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
