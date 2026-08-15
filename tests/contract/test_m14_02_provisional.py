"""Focused schema and safe-failure smoke for provisional M14-02."""

from typing import cast

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from glio_proteogen.contracts.m14_02 import (
    M1402_OUTPUT_MEDIA_TYPE,
    M1402_PROVISIONAL_ABI,
    ApplicableMechanism,
    ContextDimension,
    ContextObservation,
    ContextObservationStatus,
    MechanismApplicability,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_COUNT = 8
_SOURCE_ARTIFACT = ArtifactReference(
    artifact_id="source-1",
    version="1.0.0",
    digest="sha256:" + "a" * 64,
    media_type="application/json",
)


def _metadata(schema: object) -> dict[str, object]:
    document = cast("dict[str, object]", schema)
    return cast("dict[str, object]", document["x-glio-contract"])


def test_provisional_schemas_preserve_protein_subtype_controls() -> None:
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
        metadata = _metadata(schema)
        assert metadata["provisionalAbi"] is True
        assert metadata["conflictPreservationRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert _metadata(schemas["output"])["outputMediaType"] == M1402_OUTPUT_MEDIA_TYPE
    assert M1402_PROVISIONAL_ABI is True


def test_supported_context_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        ContextObservation(
            observation_id="obs-1",
            dimension=ContextDimension.SUBTYPE,
            value="candidate subtype",
            status=ContextObservationStatus.SUPPORTED,
            source_artifact=_SOURCE_ARTIFACT,
        )


def test_unknown_mechanism_is_not_a_negative_finding() -> None:
    mechanism = ApplicableMechanism(
        mechanism_id="mechanism-1",
        label="Context-dependent mechanism",
        applicability=MechanismApplicability.UNKNOWN,
        rationale="The declared context is outside the supported domain.",
    )
    assert mechanism.applicability is MechanismApplicability.UNKNOWN
