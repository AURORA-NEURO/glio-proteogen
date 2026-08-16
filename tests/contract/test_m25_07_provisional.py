"""Focused smoke coverage for the provisional M25-07 contract spine."""

from typing import Any, Final, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m25_07 import (
    M2507_M2506_INPUT_MEDIA_TYPE,
    M2507_OUTPUT_MEDIA_TYPE,
    M2507_PROVISIONAL_ABI,
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


def test_m25_07_provisional_schema_and_safe_fallback() -> None:
    schemas = contract_json_schemas()
    metadata = [cast("dict[str, Any]", schema["x-glio-contract"]) for schema in schemas.values()]
    assert len(schemas) == EXPECTED_SCHEMA_COUNT
    assert all(item["provisionalAbi"] is M2507_PROVISIONAL_ABI for item in metadata)
    request_metadata = cast("dict[str, Any]", schemas["request"]["x-glio-contract"])
    assert request_metadata["outputMediaType"] == M2507_OUTPUT_MEDIA_TYPE
    assert request_metadata["upstreamInputMediaType"] == M2507_M2506_INPUT_MEDIA_TYPE
    assert request_metadata["primaryArchitecture"] == "longitudinal_state_space"
    assert request_metadata["alternateArchitecture"] == "longitudinal_state_space"
    assert request_metadata["pendingOwnerConfirmation"] is True

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
