"""Adversarial contract and descriptor coverage for M08-06."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m08_06 import (
    M0806_MAX_COMPONENTS,
    M0806_OUTPUT_MEDIA_TYPE,
    M0806_PROVISIONAL_ABI,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyDimension,
    contract_json_schemas,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition import (  # noqa: E501
    M0806Plugin,
    M0806Service,
)

_SCHEMA_COUNT = 7
_NOMINAL_COVERAGE = 0.9


def test_schema_advertises_explicit_provisional_safety_boundary() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M0806_OUTPUT_MEDIA_TYPE
    assert metadata["sevenUncertaintyDimensionsRequired"] is True
    assert metadata["allOmicsFusion"] is False
    assert metadata["kinaseActivity"] is False


def test_descriptor_freezes_owner_gate_and_prohibited_outputs() -> None:
    descriptor = M0806Plugin(M0806Service()).descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M08-06"
    assert descriptor.owner == "Quality engineering"
    assert descriptor.version == "0.1.0-provisional"
    assert "kinase state" in " ".join(descriptor.prohibited_outputs)
    assert M0806_PROVISIONAL_ABI is True


def test_sensitivity_requires_ordered_coverage_inside_gate() -> None:
    envelope = SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        lower_bound=0.86,
        upper_bound=0.94,
        observed_coverage=0.90,
        rationale="Synthetic coverage is within the provisional 85-95 percent gate.",
    )
    assert envelope.observed_coverage == _NOMINAL_COVERAGE
    assert len(tuple(UncertaintyDimension)) == M0806_MAX_COMPONENTS
    with pytest.raises(ValueError, match="ordered"):
        SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            lower_bound=0.96,
            upper_bound=0.90,
            observed_coverage=0.90,
            rationale="Invalid ordering.",
        )
