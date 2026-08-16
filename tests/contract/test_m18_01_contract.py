"""Focused contract/schema smoke for provisional M18-01."""

from glio_proteogen.contracts.m18_01 import (
    M1801_OUTPUT_MEDIA_TYPE,
    M1801_PROVISIONAL_ABI,
    CompatibilityRule,
    UpstreamSourceKind,
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
        claim="Caller-declared compatibility evidence.",
    )


def test_provisional_schemas_preserve_typed_resolution_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["typedDiscoveryRequired"]
        and schema["x-glio-contract"]["versionCompatibilityRequired"]
        and schema["x-glio-contract"]["consentRequired"]
        and schema["x-glio-contract"]["intendedUseRequired"]
        and schema["x-glio-contract"]["supportRequired"]
        and schema["x-glio-contract"]["provenancePreserved"]
        and schema["x-glio-contract"]["typedRejectionsRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "biomarker panel"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1801_OUTPUT_MEDIA_TYPE
    assert M1801_PROVISIONAL_ABI is True


def test_compatibility_rule_keeps_required_source_and_intended_use_typed() -> None:
    rule = CompatibilityRule(
        rule_id="rule-1",
        name="Spatial proteomics compatibility",
        required_source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
        required_media_type="application/vnd.glio-proteogen.source+json",
        required_intended_use="biomarker panel export",
        evidence=(_evidence(),),
    )
    assert rule.required_source_kind is UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME
    assert rule.required_intended_use == "biomarker panel export"
