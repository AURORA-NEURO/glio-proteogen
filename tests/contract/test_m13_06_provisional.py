"""Focused schema and bounded-response smoke for provisional M13-06."""

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m13_06 import (
    M1306_OUTPUT_MEDIA_TYPE,
    M1306_PROVISIONAL_ABI,
    PerturbationResponse,
    PerturbationResponseStatus,
    SensitivityMetric,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8
_EVIDENCE = {
    "reference": {
        "artifact_id": "evidence-1",
        "version": "1.0.0",
        "digest": "sha256:" + "a" * 64,
        "media_type": "application/json",
    },
    "role": "evidence",
    "claim": "Locked perturbation benchmark evidence.",
}


def test_provisional_schemas_require_bounded_assumptions() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "scenario",
        "response",
        "sensitivity-surface",
        "configuration",
        "policy",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["boundedPerturbationRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1306_OUTPUT_MEDIA_TYPE
    assert M1306_PROVISIONAL_ABI is True


def test_response_delta_and_envelope_are_closed() -> None:
    with pytest.raises(ValueError, match="delta must match"):
        PerturbationResponse(
            scenario_id="scenario-1",
            status=PerturbationResponseStatus.EVALUATED,
            metric=SensitivityMetric.ABSOLUTE_DELTA,
            baseline_response=0.2,
            perturbed_response=0.5,
            delta=0.1,
            envelope_lower=0.0,
            envelope_upper=1.0,
            evidence=(_EVIDENCE,),
        )


def test_abstained_response_has_no_numeric_claim() -> None:
    with pytest.raises(ValueError, match="evaluated perturbation response"):
        PerturbationResponse(
            scenario_id="scenario-2",
            status=PerturbationResponseStatus.EVALUATED,
            metric=SensitivityMetric.PROBABILITY_DELTA,
            baseline_response=0.4,
            perturbed_response=0.4,
            delta=0.0,
            envelope_lower=0.0,
            envelope_upper=1.0,
        )
