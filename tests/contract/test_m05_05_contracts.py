"""Frozen contract/schema checkpoint for GLIO-PROTEOGEN-M05-05."""

from __future__ import annotations

import json
from typing import cast

import pytest
from evals.m05_03.run import canonical_smoke as m0503_canonical_smoke
from pydantic import ValidationError

import glio_proteogen.contracts.m05_05 as m0505
from glio_proteogen.contracts.m05_05 import (
    DetectPtmLocalizationArtifactsRequest,
    PtmLocalizationArtifactDetectorClass,
    PtmLocalizationArtifactDisposition,
    PtmLocalizationArtifactObservationState,
    PtmLocalizationArtifactPosteriorState,
    PtmLocalizationArtifactThreshold,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "threshold",
    "profile",
    "evidence-event",
    "evidence-ledger",
    "evidence-ledger-binding",
    "artifact-posterior",
    "contamination-flag",
    "exclusion-mask-entry",
    "finding",
    "receipt",
)
_MAX_SIGNED_64_BIT_INTEGER = 9_223_372_036_854_775_807


def _artifact_reference(label: str, media_type: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.{label * 64}",
        version="1.0.0",
        digest=f"sha256:{label * 64}",
        media_type=media_type,
    )


@pytest.mark.contract
def test_schema_inventory_ids_order_and_boundary_metadata_are_frozen() -> None:
    schemas = contract_json_schemas()

    assert tuple(schemas) == _SCHEMA_NAMES
    for name, schema in schemas.items():
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == (
            "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-05:1.0.0:" + name
        )
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata == {
            "moduleId": "GLIO-PROTEOGEN-M05-05",
            "contractVersion": "1.0.0",
            "owner": "Scientific engineering",
            "safetyClass": "S2",
            "gate": "G1",
            "strict": True,
            "aggregateEvidenceOnly": True,
            "eventSourced": True,
            "openSetAbstention": True,
            "rateScale": 1_000_000,
            "externalContentTraversal": False,
            "rawPayload": False,
            "calibratedProbability": False,
            "identityInference": False,
            "consentInference": False,
            "ptmLocalizationInference": False,
            "modificationLocalization": False,
            "proteogenomicStateInference": False,
            "proteotypeInference": False,
            "proteinLevelSubtypeInference": False,
            "kinaseActivityInference": False,
            "allOmicsFusion": False,
            "treatmentRecommendation": False,
            "variantPeptideEmission": False,
            "parentTarget": "variant_peptide",
            "outputMediaType": "application/vnd.glio-proteogen.m05-05+json",
            **({"maxRequestBytes": 4 * 1024 * 1024} if name == "request" else {}),
        }
        json.dumps(schema)


@pytest.mark.contract
def test_frozen_names_enums_and_capacity_acceptance_constants() -> None:
    assert m0505.M0505_MODULE_ID == "GLIO-PROTEOGEN-M05-05"
    assert m0505.M0505_OPERATION == "detect_ptm_localization_artifacts"
    assert m0505.M0505_PARENT == "variant_peptide"
    assert m0505.M0505_OUTPUT_MEDIA_TYPE == "application/vnd.glio-proteogen.m05-05+json"
    assert tuple(item.value for item in PtmLocalizationArtifactDetectorClass) == (
        "technical_artifact",
        "contamination",
        "barcode_index",
        "batch_effect",
        "low_complexity",
        "mapping_error",
        "context_specific_false_positive",
    )
    assert tuple(item.value for item in PtmLocalizationArtifactDisposition) == (
        "cleared",
        "quarantined",
        "abstained",
    )
    assert tuple(item.value for item in PtmLocalizationArtifactPosteriorState) == (
        "clear",
        "suspected",
        "detected",
        "indeterminate",
    )
    assert tuple(item.value for item in PtmLocalizationArtifactObservationState) == (
        "observed",
        "missing",
        "not_applicable",
        "unsupported",
    )
    assert (
        m0505.M0505_DETECTOR_CLASS_COUNT,
        m0505.M0505_MAX_TARGETS,
        m0505.M0505_MAX_EVENTS,
        m0505.M0505_MAX_FLAGS,
        m0505.M0505_MAX_FINDINGS,
        m0505.M0505_MAX_PROFILES,
        m0505.M0505_MAX_APPROVED_VERSIONS,
        m0505.M0505_MAX_EVENT_EVIDENCE,
        m0505.M0505_MAX_EVIDENCE,
    ) == (7, 64, 448, 128, 10, 16, 32, 8, 17)
    assert m0505.M0505_MAX_COUNT == _MAX_SIGNED_64_BIT_INTEGER
    assert (
        m0505.M0505_SEEDED_SENSITIVITY_FLOOR_PPM,
        m0505.M0505_FALSE_EXCLUSION_CEILING_PPM,
        m0505.M0505_COVERAGE_LOWER_PPM,
        m0505.M0505_COVERAGE_UPPER_PPM,
    ) == (900_000, 50_000, 850_000, 950_000)
    assert (
        m0505.M0505_BENCHMARK_ITERATIONS,
        m0505.M0505_BENCHMARK_WARMUPS,
        m0505.M0505_MEAN_BUDGET_NS,
        m0505.M0505_P95_BUDGET_NS,
    ) == (25, 1, 2_000_000_000, 3_000_000_000)


@pytest.mark.contract
def test_threshold_is_strict_closed_and_immutable() -> None:
    threshold = PtmLocalizationArtifactThreshold(
        detector_class=PtmLocalizationArtifactDetectorClass.TECHNICAL_ARTIFACT,
        review_threshold_ppm=250_000,
        exclusion_threshold_ppm=750_000,
        required=True,
        evidence=_artifact_reference("1", "application/vnd.glio-proteogen.m05-05.threshold+json"),
    )
    payload = threshold.model_dump(mode="python", exclude_none=False)
    payload["review_threshold_ppm"] = "250000"
    with pytest.raises(ValidationError):
        PtmLocalizationArtifactThreshold.model_validate(payload, strict=True)

    extra = threshold.model_dump(mode="python", exclude_none=False)
    extra["inferred_negative"] = True
    with pytest.raises(ValidationError):
        PtmLocalizationArtifactThreshold.model_validate(extra, strict=True)

    with pytest.raises(ValidationError):
        threshold.required = False  # type: ignore[misc]


@pytest.mark.contract
def test_request_schema_requires_full_strict_m0503_replay() -> None:
    schema = contract_json_schema("request")
    required = cast("list[str]", schema["required"])
    properties = cast("dict[str, object]", schema["properties"])
    definitions = cast("dict[str, object]", schema["$defs"])

    assert "raw_input_result" in required
    assert properties["raw_input_result"] == {
        "$ref": "#/$defs/PtmLocalizationRawInputValidationResult"
    }
    assert "PtmLocalizationRawInputValidationResult" in definitions
    raw_result = cast("dict[str, object]", definitions["PtmLocalizationRawInputValidationResult"])
    assert set(cast("list[str]", raw_result["required"])) >= {
        "request",
        "receipt",
        "disposition",
        "result_digest",
    }
    raw_receipt = cast("dict[str, object]", definitions["PtmLocalizationRawInputReceipt"])
    assert "identity_resolution_digest" in cast("list[str]", raw_receipt["required"])
    assert cast("dict[str, object]", raw_result["properties"])["disposition"] == {
        "$ref": "#/$defs/PtmLocalizationRawInputDisposition"
    }


@pytest.mark.contract
def test_full_m0503_result_is_reparsed_and_stale_digest_is_rejected() -> None:
    raw_result = m0503_canonical_smoke()

    replayed = DetectPtmLocalizationArtifactsRequest.raw_input_result_is_strictly_replayed(
        raw_result
    )
    assert replayed == raw_result
    assert replayed is not raw_result

    forged = raw_result.model_copy(update={"result_digest": f"sha256:{'0' * 64}"})
    with pytest.raises(ValidationError, match="result digest"):
        DetectPtmLocalizationArtifactsRequest.raw_input_result_is_strictly_replayed(forged)


@pytest.mark.contract
def test_output_schema_exposes_only_owned_outputs_and_frozen_false_capabilities() -> None:
    schema = contract_json_schema("output")
    properties = cast("dict[str, object]", schema["properties"])

    assert set(properties) >= {
        "artifact_posteriors",
        "contamination_flags",
        "exclusion_mask",
        "support",
        "uncertainty",
        "provenance",
        "evidence",
        "limitations",
    }
    assert set(properties).isdisjoint(
        {
            "proteogenomic_state",
            "proteotype",
            "protein_level_subtype",
            "kinase_activity",
            "treatment_recommendation",
        }
    )
    for field in (
        "emits_variant_peptide",
        "emits_proteogenomic_state",
        "emits_proteotype",
        "emits_protein_level_subtype",
        "infers_identity",
        "infers_consent",
        "localizes_modification",
        "infers_kinase_activity",
        "performs_all_omics_fusion",
        "recommends_treatment",
        "mutates_upstream",
    ):
        assert cast("dict[str, object]", properties[field])["const"] is False
