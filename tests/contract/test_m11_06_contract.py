"""Focused contract/schema smoke for provisional M11-06."""

from math import inf

import pytest

from glio_proteogen.contracts.m11_06 import (
    M1106_OUTPUT_MEDIA_TYPE,
    M1106_PROVISIONAL_ABI,
    PerturbationKind,
    PerturbationResponseStatus,
    PerturbationSpecification,
    SensitivityResponse,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_bounded_sensitivity_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["boundedResponsesRequired"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["assumptionsRequired"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["typedReplicateSensitivity"] for schema in schemas.values()
    )
    assert all(schema["x-glio-contract"]["deterministicBootstrap"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1106_OUTPUT_MEDIA_TYPE
    assert M1106_PROVISIONAL_ABI is True


def test_bounded_response_requires_ordered_envelope() -> None:
    response = SensitivityResponse(
        scenario_id="scenario.base",
        status=PerturbationResponseStatus.BOUNDED,
        response_value=0.5,
        lower_bound=0.2,
        upper_bound=0.8,
        assumptions=("Locked baseline assumption.",),
    )
    assert response.lower_bound <= response.response_value <= response.upper_bound
    assert PerturbationKind.MECHANISM_STRESS.value == "mechanism_stress"
    with pytest.raises(ValueError, match="bounded response"):
        SensitivityResponse(
            scenario_id="scenario.bad",
            status=PerturbationResponseStatus.BOUNDED,
            assumptions=("Missing response bounds.",),
        )


def test_typed_perturbation_requires_finite_paired_replicates() -> None:
    base = {
        "perturbation_id": "scenario.typed",
        "kind": PerturbationKind.IN_SILICO,
        "target_ids": ("target.1",),
        "parameter": "protein_abundance",
        "baseline_value": "1.0",
        "perturbed_value": "1.2",
        "rationale": "Replicate validation.",
    }
    with pytest.raises(ValueError, match="supplied together"):
        PerturbationSpecification.model_validate(
            {**base, "baseline_measurements": (1.0, 1.1, 1.2)}
        )
    with pytest.raises(ValueError, match="at least three"):
        PerturbationSpecification.model_validate(
            {**base, "baseline_measurements": (1.0, 1.1), "perturbed_measurements": (1.2, 1.3)}
        )
    with pytest.raises(ValueError, match="finite"):
        PerturbationSpecification.model_validate(
            {
                **base,
                "baseline_measurements": (1.0, 1.1, inf),
                "perturbed_measurements": (1.2, 1.3, 1.4),
            }
        )


def test_non_bounded_response_rejects_numeric_sensitivity_fields() -> None:
    with pytest.raises(ValueError, match="non-bounded"):
        SensitivityResponse(
            scenario_id="scenario.abstained",
            status=PerturbationResponseStatus.ABSTAINED,
            raw_effect_delta=0.2,
            assumptions=("No surface.",),
        )
