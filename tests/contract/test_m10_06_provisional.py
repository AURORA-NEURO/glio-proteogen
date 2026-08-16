"""Focused contract/schema smoke for provisional M10-06."""

import pytest

from glio_proteogen.contracts.m10_06 import (
    M1006_MAX_COMPONENTS,
    M1006_NOMINAL_COVERAGE,
    M1006_OUTPUT_MEDIA_TYPE,
    M1006_PROVISIONAL_ABI,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDimension,
    UncertaintyFindingCode,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import EstimateState, UncertaintyEstimate

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_seven_dimensions_and_sensitivity() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["sevenUncertaintyDimensionsRequired"]
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1006_OUTPUT_MEDIA_TYPE
    assert M1006_PROVISIONAL_ABI is True


def test_sensitivity_envelope_enforces_provisional_coverage_gate() -> None:
    envelope = SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        lower_bound=0.86,
        upper_bound=0.94,
        observed_coverage=0.9,
        rationale="Synthetic smoke coverage remains within the provisional gate.",
    )
    assert envelope.nominal_coverage == M1006_NOMINAL_COVERAGE
    assert len(tuple(UncertaintyDimension)) == M1006_MAX_COMPONENTS


def test_decomposition_rejects_missing_dimension_instead_of_coercing() -> None:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.2,
        rationale="Synthetic smoke estimate.",
    )
    component = UncertaintyComponent(
        dimension=UncertaintyDimension.MEASUREMENT,
        estimate=estimate,
        rationale="Measurement uncertainty is represented explicitly.",
    )
    with pytest.raises(ValueError, match="all seven dimensions"):
        UncertaintyDecomposition(
            decomposition_id="smoke",
            components=(component,) * M1006_MAX_COMPONENTS,
            method="proteogenomic_vae",
            model_reference={
                "artifact_id": "vae",
                "version": "1.0.0",
                "digest": "sha256:" + "0" * 64,
                "media_type": "application/vnd.glio-proteogen.model+json",
            },
        )
    assert UncertaintyFindingCode.PROVISIONAL_ABI_PENDING_REVIEW.value
