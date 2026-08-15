"""Focused schema and immutable-link smoke for provisional M27-02."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m27_02 import (
    M2702_M2701_INPUT_MEDIA_TYPE,
    M2702_OUTPUT_MEDIA_TYPE,
    M2702_PROVISIONAL_ABI,
    LineageNodeKind,
    LineageRelation,
    LineageStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8
_NODE_KIND_COUNT = 7


def test_provisional_schemas_require_immutable_lineage_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "graph",
        "node",
        "edge",
        "bundle",
        "finding",
        "safe-failure",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["immutableLineageRequired"] is True
        assert metadata["queryableGraphRequired"] is True
        assert metadata["exactVersionTraceabilityRequired"] is True
        assert metadata["reproducibilityBundleRequired"] is True
        assert metadata["brokenLinkRejectionRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "complex activity"
        assert metadata["upstreamInputMediaType"] == M2702_M2701_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2702_OUTPUT_MEDIA_TYPE
    assert M2702_PROVISIONAL_ABI is True


def test_lineage_kinds_and_resolution_states_are_explicit() -> None:
    assert len(tuple(LineageNodeKind)) == _NODE_KIND_COUNT
    assert LineageRelation.DERIVED_FROM.value == "derived_from"
    assert LineageStatus.ABSTAINED.value == "abstained"
