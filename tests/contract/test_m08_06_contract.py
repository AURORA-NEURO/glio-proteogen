"""Focused contract/schema smoke for provisional M08-06."""

from glio_proteogen.contracts.m08_06 import (
    M0806_MAX_COMPONENTS,
    M0806_NOMINAL_COVERAGE,
    M0806_OUTPUT_MEDIA_TYPE,
    M0806_PROVISIONAL_ABI,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyDimension,
    contract_json_schemas,
)

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
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0806_OUTPUT_MEDIA_TYPE
    assert M0806_PROVISIONAL_ABI is True


def test_sensitivity_envelope_enforces_provisional_coverage_gate() -> None:
    envelope = SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        lower_bound=0.86,
        upper_bound=0.94,
        observed_coverage=0.9,
        rationale="Synthetic smoke coverage remains within the provisional gate.",
    )
    assert envelope.nominal_coverage == M0806_NOMINAL_COVERAGE
    assert len(tuple(UncertaintyDimension)) == M0806_MAX_COMPONENTS
