"""Focused contract/schema smoke for provisional M22-07."""

from typing import Any, cast

import pytest

from glio_proteogen.contracts.m22_07 import (
    M2207_DOSSIER_SHA256,
    M2207_DOSSIER_SLICE,
    M2207_M2206_INPUT_MEDIA_TYPE,
    M2207_OUTPUT_MEDIA_TYPE,
    M2207_PROVISIONAL_ABI,
    EvaluationStatus,
    FallbackScenario,
    OperationalConfiguration,
    OperationalDimension,
    OperationalMetric,
    OperationalStatus,
    contract_json_schemas,
    result_identifier,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_human_factors_safety_controls() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["reviewerComprehensionRequired"]
        and schema["x-glio-contract"]["automationBiasAssessmentRequired"]
        and schema["x-glio-contract"]["throughputLatencyRequired"]
        and schema["x-glio-contract"]["downtimeRecoveryRequired"]
        and schema["x-glio-contract"]["fallbackRequired"]
        and schema["x-glio-contract"]["userInterpretationRequired"]
        and schema["x-glio-contract"]["operationalObjectivesRequired"]
        and schema["x-glio-contract"]["humanReviewRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "protein-RNA discordance"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2207_OUTPUT_MEDIA_TYPE
    assert M2207_PROVISIONAL_ABI is True


def test_operational_dimensions_and_safe_states_are_explicit() -> None:
    assert OperationalDimension.AUTOMATION_BIAS.value == "automation_bias"
    assert OperationalDimension.REVIEWER_COMPREHENSION.value == "reviewer_comprehension"
    assert OperationalDimension.FALLBACK.value == "fallback"
    assert OperationalStatus.NOT_EVALUABLE.value == "not_evaluable"
    assert EvaluationStatus.ABSTAINED.value == "abstained"
    with pytest.raises(AssertionError):
        assert cast("object", EvaluationStatus.ABSTAINED) is cast(
            "object", EvaluationStatus.EVALUATED
        )


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=ArtifactReference(
            artifact_id="m2207-evidence",
            version="0.1.0",
            digest="sha256:" + "a" * 64,
            media_type="application/octet-stream",
        ),
        role="evidence",
        claim="Caller-declared operational evidence.",
    )


def test_contract_metadata_records_authority_and_media_boundary() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert all(
        schema["x-glio-contract"]["dossierSha256"] == M2207_DOSSIER_SHA256
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["dossierSlice"] == M2207_DOSSIER_SLICE
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["inputMediaType"] == M2207_M2206_INPUT_MEDIA_TYPE
        for schema in schemas.values()
    )


def test_metric_status_cannot_hide_a_threshold_failure() -> None:
    with pytest.raises(ValueError, match="within its declared tolerance"):
        OperationalMetric(
            metric_id="metric-1",
            dimension=OperationalDimension.LATENCY,
            metric_name="latency",
            observed_value=12.0,
            target_value=1.0,
            tolerance=0.5,
            sample_size=10,
            status=OperationalStatus.PASS,
            evidence=(_evidence(),),
        )
    with pytest.raises(ValueError, match="exceed its declared tolerance"):
        OperationalMetric(
            metric_id="metric-2",
            dimension=OperationalDimension.LATENCY,
            metric_name="latency",
            observed_value=1.0,
            target_value=1.0,
            tolerance=0.5,
            sample_size=10,
            status=OperationalStatus.FAIL,
            evidence=(_evidence(),),
        )


def test_fallback_and_configuration_closures_are_fail_closed() -> None:
    with pytest.raises(ValueError, match="unavailable fallback cannot pass"):
        FallbackScenario(
            scenario_id="fallback-1",
            dimension=OperationalDimension.FALLBACK,
            trigger="service unavailable",
            fallback_path="manual review",
            recovery_seconds=3.0,
            fallback_available=False,
            status=OperationalStatus.PASS,
            evidence=(_evidence(),),
        )
    dimensions = tuple(OperationalDimension)
    with pytest.raises(ValueError, match="must be unique"):
        OperationalConfiguration(
            configuration_id="configuration-1",
            version="0.1.0",
            required_dimensions=(*dimensions[:-1], dimensions[0]),
            evidence=(_evidence(),),
        )


def test_result_identifier_is_deterministic_and_replay_bound() -> None:
    request = {
        "operation": "evaluate_protein_rna_discordance_human_factors_operational",
        "request_id": "request-1",
        "source_artifacts": ["sha256:" + "b" * 64],
    }
    identifier = result_identifier(request)
    assert identifier == result_identifier(dict(request))
    assert identifier.startswith("result.")
    assert identifier != result_identifier({**request, "request_id": "request-2"})
