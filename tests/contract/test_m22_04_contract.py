"""Focused contract/schema smoke for provisional M22-04."""

from typing import Any, cast

from glio_proteogen.contracts.m22_04 import (
    M2204_OUTPUT_MEDIA_TYPE,
    M2204_PROVISIONAL_ABI,
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


def test_provisional_schemas_preserve_external_transport_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    for schema in schemas.values():
        metadata = cast("dict[str, Any]", schema["x-glio-contract"])
        assert cast("str", schema["$schema"]).endswith("2020-12/schema")
        assert metadata["provisionalAbi"] is True
        assert metadata["pendingOwnerConfirmation"] is True
        assert metadata["externalTransportRequired"] is True
        assert metadata["independentSiteLabPlatformValidationRequired"] is True
        assert metadata["treatmentEraPopulationDiseaseClassSpecimenRequired"] is True
        assert metadata["calibrationFloorsRequired"] is True
        assert metadata["supportDomainNarrowingAllowed"] is True
        assert metadata["provenanceRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "protein-RNA discordance"
    output_metadata = cast("dict[str, Any]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2204_OUTPUT_MEDIA_TYPE
    assert M2204_PROVISIONAL_ABI is True


def test_transport_validation_keeps_dimension_and_identity_typed() -> None:
    validation = TransportValidation(
        validation_id="validation-1",
        dimension=TransportDimension.SITE,
        source_domain="site-A",
        target_domain="site-B",
        assay_or_platform="orthogonal immunoassay",
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
    assert validation.dimension is TransportDimension.SITE
    assert validation.identity_verified is True
