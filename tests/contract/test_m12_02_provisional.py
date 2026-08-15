"""Focused schema and safe-failure smoke for provisional M12-02."""

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m12_02 import (
    M1202_OUTPUT_MEDIA_TYPE,
    M1202_PROVISIONAL_ABI,
    ApplicableMechanism,
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    MechanismApplicability,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_preserve_context_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "observation",
        "profile",
        "mechanism",
        "configuration",
        "policy",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["conflictPreservationRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1202_OUTPUT_MEDIA_TYPE
    assert M1202_PROVISIONAL_ABI is True


def test_supported_context_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        ContextObservation(
            observation_id="obs-1",
            dimension=ContextDimension.SUBTYPE,
            value="candidate subtype",
            status=ContextObservationStatus.SUPPORTED,
            source_artifact={
                "artifact_id": "source-1",
                "version": "1.0.0",
                "digest": "sha256:" + "a" * 64,
                "media_type": "application/json",
            },
        )


def test_unknown_mechanism_is_not_a_negative_finding() -> None:
    mechanism = ApplicableMechanism(
        mechanism_id="mechanism-1",
        label="Context-dependent mechanism",
        applicability=MechanismApplicability.UNKNOWN,
        rationale="The declared context is outside the supported domain.",
    )
    assert mechanism.applicability is MechanismApplicability.UNKNOWN
