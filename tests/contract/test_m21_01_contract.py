"""Focused contract/schema smoke for provisional M21-01."""

from glio_proteogen.contracts.m21_01 import (
    M2101_OUTPUT_MEDIA_TYPE,
    M2101_PROVISIONAL_ABI,
    EndpointDefinition,
    ReferenceKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 9


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=ArtifactReference(
            artifact_id="artifact-1",
            version="0.1.0",
            digest="sha256:" + "a" * 64,
            media_type="application/octet-stream",
        ),
        role="evidence",
        claim="Caller-declared benchmark evidence.",
    )


def test_provisional_schemas_preserve_reference_truth_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["referenceTruthRequired"]
        and schema["x-glio-contract"]["benchmarkPackageRequired"]
        and schema["x-glio-contract"]["controlsRequired"]
        and schema["x-glio-contract"]["adjudicationRequired"]
        and schema["x-glio-contract"]["endpointDefinitionRequired"]
        and schema["x-glio-contract"]["provenanceRequired"]
        and schema["x-glio-contract"]["inclusionAndChallengeSetRequired"]
        and schema["x-glio-contract"]["leakageAuditRequired"]
        and schema["x-glio-contract"]["lockProcedureRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "complex activity"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2101_OUTPUT_MEDIA_TYPE
    assert M2101_PROVISIONAL_ABI is True


def test_endpoint_definition_keeps_parent_and_metric_typed() -> None:
    endpoint = EndpointDefinition(
        endpoint_id="endpoint-1",
        name="Complex activity reference endpoint",
        definition="Reference truth for complex activity.",
        metric="calibration_error",
        acceptance_tolerance="Within preregistered tolerance.",
        evidence=(_evidence(),),
    )
    assert endpoint.target == "complex activity"
    assert endpoint.metric == "calibration_error"
    assert ReferenceKind.CHALLENGE_SET.value == "challenge_set"
