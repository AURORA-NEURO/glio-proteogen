"""Focused contract/schema smoke for provisional M21-04."""

from glio_proteogen.contracts.m21_04 import (
    M2104_OUTPUT_MEDIA_TYPE,
    M2104_PROVISIONAL_ABI,
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
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["externalTransportRequired"]
        and schema["x-glio-contract"]["independentSiteLabPlatformValidationRequired"]
        and schema["x-glio-contract"]["treatmentEraPopulationDiseaseClassSpecimenRequired"]
        and schema["x-glio-contract"]["calibrationFloorsRequired"]
        and schema["x-glio-contract"]["supportDomainNarrowingAllowed"]
        and schema["x-glio-contract"]["provenanceRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "complex activity"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2104_OUTPUT_MEDIA_TYPE
    assert M2104_PROVISIONAL_ABI is True


def test_transport_validation_keeps_dimension_and_identity_typed() -> None:
    validation = TransportValidation(
        validation_id="validation-1",
        dimension=TransportDimension.SITE,
        source_domain="site-A",
        target_domain="site-B",
        assay_or_platform="proteome platform",
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
