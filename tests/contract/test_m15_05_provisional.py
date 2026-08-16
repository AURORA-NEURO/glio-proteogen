"""Focused schema and temporal-ordering smoke for provisional M15-05."""

from datetime import UTC, datetime

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m15_05 import (
    M1505_DOSSIER_SHA256,
    M1505_DOSSIER_SLICE,
    M1505_OUTPUT_MEDIA_TYPE,
    M1505_PROVISIONAL_ABI,
    ChangePoint,
    ChangePointStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_ordering_and_leakage_controls() -> None:
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
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["temporalOrderingRequired"] is True
        assert metadata["futureLeakageBlocked"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1505_OUTPUT_MEDIA_TYPE
    assert M1505_PROVISIONAL_ABI is True
    assert M1505_DOSSIER_SHA256 == (
        "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M1505_DOSSIER_SLICE.endswith(":5252-5295")
    assert all(
        schema["x-glio-contract"]["dossierSlice"] == M1505_DOSSIER_SLICE
        for schema in schemas.values()
    )


def test_detected_change_point_requires_explicit_evidence() -> None:
    with pytest.raises(ValueError, match="detected change point"):
        ChangePoint(
            change_point_id="cp-1",
            sequence=1,
            status=ChangePointStatus.DETECTED,
            before_state_id="state-a",
            after_state_id="state-b",
            posterior_probability=0.8,
            rationale="A complex activity transition is detected.",
        )


def test_temporal_fixture_is_aware() -> None:
    assert datetime(2026, 1, 1, tzinfo=UTC).tzinfo is not None
