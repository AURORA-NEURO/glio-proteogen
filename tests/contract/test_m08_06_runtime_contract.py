"""Adversarial contract and descriptor coverage for M08-06."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m08_06 import (
    M0806_MAX_COMPONENTS,
    M0806_OUTPUT_MEDIA_TYPE,
    M0806_PROVISIONAL_ABI,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
    contract_json_schemas,
    expected_uncertainty,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.models import ArtifactReference, EstimateState, UncertaintyEstimate
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition import (  # noqa: E501
    M0806Plugin,
    M0806Service,
)
from tests.modules.c08_transcript_protein_discordance.test_m08_06_uncertainty import _request

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


def test_contract_rejects_incomplete_dimensions_and_invalid_envelopes() -> None:
    component = UncertaintyComponent(
        dimension=UncertaintyDimension.MEASUREMENT,
        estimate=UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale="No calibration.",
        ),
        rationale="Explicitly unresolved.",
    )
    with pytest.raises(ValueError, match="all seven"):
        UncertaintyDecomposition(
            decomposition_id="decomposition.invalid",
            components=(component,) * M0806_MAX_COMPONENTS,
            method="rule",
            model_reference=ArtifactReference(
                artifact_id="model.invalid",
                version="1.0.0",
                digest="sha256:" + "a" * 64,
                media_type="application/octet-stream",
            ),
        )
    for values, message in (
        ({"status": SensitivityEnvelopeStatus.EVALUATED, "lower_bound": 0.9}, "bounds"),
        (
            {
                "status": SensitivityEnvelopeStatus.EVALUATED,
                "lower_bound": 0.80,
                "upper_bound": 0.90,
                "observed_coverage": 0.80,
            },
            "85-95",
        ),
        (
            {
                "status": SensitivityEnvelopeStatus.EVALUATED,
                "lower_bound": 0.86,
                "upper_bound": 0.94,
                "observed_coverage": 0.90,
                "nominal_coverage": 0.95,
            },
            "nominal",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            SensitivityEnvelope(rationale="invalid envelope", **values)


def test_contract_closes_policy_result_and_digest_paths() -> None:
    request = _request()
    with pytest.raises(ValueError, match="nominal 90"):
        type(request.policy).model_validate(
            request.policy.model_dump(mode="python") | {"nominal_coverage": 0.95},
            strict=True,
        )
    result = M0806Service().execute(request)
    with pytest.raises(ValueError, match="request digest"):
        type(result).model_validate(
            result.model_dump(mode="python") | {"request_digest": "sha256:" + "0" * 64},
            strict=True,
        )
    with pytest.raises(ValueError, match="decomposed result"):
        type(result).model_validate(
            result.model_dump(mode="python")
            | {"status": UncertaintyDecompositionStatus.DECOMPOSED},
            strict=True,
        )
    with pytest.raises(ValueError, match="result digest"):
        type(result).model_validate(
            result.model_dump(mode="python") | {"result_digest": "sha256:" + "0" * 64},
            strict=True,
        )
    assert result_payload_digest(result) == result.result_digest
    assert verify_result_digest(result) is True
    assert verify_result_digest(object()) is False
    assert verify_result_digest({}) is False
    assert expected_uncertainty().transport.state is EstimateState.NOT_ESTIMABLE
