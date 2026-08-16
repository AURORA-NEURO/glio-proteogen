"""Focused contract/schema smoke for provisional M25-04."""

from typing import Any, cast

from glio_proteogen.contracts.m25_04 import (
    M2504_OUTPUT_MEDIA_TYPE,
    M2504_PROVISIONAL_ABI,
    TransportDimension,
    TransportValidation,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EstimateState,
    EvidenceReference,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_SCHEMA_COUNT = 8


def _metadata(schema: dict[str, object]) -> dict[str, Any]:
    return cast("dict[str, Any]", schema["x-glio-contract"])


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=ArtifactReference(
            artifact_id="artifact-1",
            version="0.1.0",
            digest="sha256:" + "a" * 64,
            media_type="application/octet-stream",
        ),
        role="evidence",
        claim="Caller-declared transport evidence.",
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.5,
        rationale="Caller-declared transport uncertainty.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def test_provisional_schemas_preserve_proteotype_transport_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(str(schema["$schema"]).endswith("2020-12/schema") for schema in schemas.values())
    assert all(_metadata(schema)["provisionalAbi"] for schema in schemas.values())
    assert all(_metadata(schema)["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        _metadata(schema)["structureAwareProteoformModelRequired"]
        and _metadata(schema)["externalTransportRequired"]
        and _metadata(schema)["independentSiteLabPlatformValidationRequired"]
        and _metadata(schema)["treatmentEraPopulationDiseaseClassSpecimenRequired"]
        and _metadata(schema)["calibrationFloorsRequired"]
        and _metadata(schema)["supportDomainNarrowingAllowed"]
        and _metadata(schema)["provenanceRequired"]
        and _metadata(schema)["humanReviewRequired"]
        and _metadata(schema)["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(_metadata(schema)["parentTarget"] == "proteotype" for schema in schemas.values())
    assert _metadata(schemas["output"])["outputMediaType"] == M2504_OUTPUT_MEDIA_TYPE
    assert M2504_PROVISIONAL_ABI is True


def test_transport_validation_keeps_dimension_and_identity_typed() -> None:
    validation = TransportValidation(
        validation_id="validation-1",
        dimension=TransportDimension.DISEASE_CLASS,
        source_domain="disease-class-A",
        target_domain="disease-class-B",
        assay_or_platform="structure-aware proteoform model",
        specimen_description="Frozen glioma specimen",
        sample_count=12,
        provenance_artifact=ArtifactReference(
            artifact_id="provenance-1",
            version="0.1.0",
            digest="sha256:" + "b" * 64,
            media_type="application/octet-stream",
        ),
        uncertainty=_uncertainty(),
        evidence=(_evidence(),),
    )
    assert validation.dimension is TransportDimension.DISEASE_CLASS
    assert validation.identity_verified is True
