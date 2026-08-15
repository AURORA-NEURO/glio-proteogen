"""Focused schema and deterministic-execution smoke for provisional M27-03."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m27_03 import (
    M2703_M2702_INPUT_MEDIA_TYPE,
    M2703_OUTPUT_MEDIA_TYPE,
    M2703_PROVISIONAL_ABI,
    ExecutionStatus,
    PipelineStatus,
    WorkflowNodeKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8
_NODE_KIND_COUNT = 4


def test_provisional_schemas_require_reproducible_execution_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "dag",
        "node",
        "edge",
        "execution",
        "package",
        "safe-failure",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["workflowDagRequired"] is True
        assert metadata["containerDigestRequired"] is True
        assert metadata["deterministicExecutionRequired"] is True
        assert metadata["retryAndCheckpointRequired"] is True
        assert metadata["environmentCaptureRequired"] is True
        assert metadata["reproducibleResultPackageRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "complex activity"
        assert metadata["upstreamInputMediaType"] == M2703_M2702_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2703_OUTPUT_MEDIA_TYPE
    assert M2703_PROVISIONAL_ABI is True


def test_workflow_states_and_node_kinds_are_explicit() -> None:
    assert len(tuple(WorkflowNodeKind)) == _NODE_KIND_COUNT
    assert ExecutionStatus.RECOVERED.value == "recovered"
    assert PipelineStatus.ABSTAINED.value == "abstained"
