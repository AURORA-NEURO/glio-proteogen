"""Focused smoke coverage for the provisional M24-07 contract spine."""

from typing import Final

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m24_07 import (
    M2407_M2406_INPUT_MEDIA_TYPE,
    M2407_OUTPUT_MEDIA_TYPE,
    M2407_PROVISIONAL_ABI,
    FallbackScenario,
    OperationalDimension,
    OperationalStatus,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

EXPECTED_SCHEMA_COUNT: Final = 7


def _evidence() -> tuple[EvidenceReference, ...]:
    reference = ArtifactReference(
        artifact_id="m2407-evidence",
        version="1.0.0",
        digest="sha256:" + "a" * 64,
        media_type="application/vnd.glio-proteogen.evidence+json",
    )
    return (EvidenceReference(reference=reference, role="evidence", claim="smoke"),)


def test_m24_07_provisional_schema_and_safe_fallback() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == EXPECTED_SCHEMA_COUNT
    assert all(
        schema["x-glio-contract"]["provisionalAbi"] is M2407_PROVISIONAL_ABI
        for schema in schemas.values()
    )
    metadata = schemas["request"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M2407_OUTPUT_MEDIA_TYPE
    assert metadata["upstreamInputMediaType"] == M2407_M2406_INPUT_MEDIA_TYPE
    assert metadata["primaryArchitecture"] == "territory_conditioned_subtype"
    assert metadata["alternateArchitecture"] == "spatial_proteotype_field"
    assert metadata["pendingOwnerConfirmation"] is True

    with pytest.raises(ValidationError, match="unavailable fallback cannot pass"):
        FallbackScenario(
            scenario_id="fallback-1",
            dimension=OperationalDimension.FALLBACK,
            trigger="challenge unsupported",
            fallback_path="abstain",
            recovery_seconds=0.0,
            fallback_available=False,
            status=OperationalStatus.PASS,
            evidence=_evidence(),
        )
