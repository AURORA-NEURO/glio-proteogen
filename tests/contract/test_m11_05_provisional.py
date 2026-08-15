"""Focused schema and temporal-ordering smoke for provisional M11-05."""

from datetime import UTC, datetime
from typing import cast

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from glio_proteogen.contracts.m11_05 import (
    M1105_M1104_RESULT_MEDIA_TYPE,
    M1105_OUTPUT_MEDIA_TYPE,
    M1105_PROVISIONAL_ABI,
    ChangePoint,
    ChangePointStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_are_strict_and_temporal() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "observation",
        "trajectory-state",
        "change-point",
        "configuration",
        "policy",
        "diagnostic",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["futureLeakageBlocked"] is True
        assert metadata["unsupportedToNegative"] is False
    output_metadata = cast("dict[str, object]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M1105_OUTPUT_MEDIA_TYPE
    assert M1105_M1104_RESULT_MEDIA_TYPE.endswith("m11-04+json")
    assert M1105_PROVISIONAL_ABI is True


def test_detected_change_point_requires_explicit_evidence() -> None:
    with pytest.raises(ValueError, match="detected change point"):
        ChangePoint(
            change_point_id="cp-1",
            sequence=1,
            status=ChangePointStatus.DETECTED,
            before_state_id="state-a",
            after_state_id="state-b",
            posterior_probability=0.8,
            rationale="A transition is detected.",
        )


def test_datetime_fixture_is_aware() -> None:
    assert datetime(2026, 1, 1, tzinfo=UTC).tzinfo is not None
