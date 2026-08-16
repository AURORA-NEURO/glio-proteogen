"""Focused contract/schema smoke for provisional M20-01."""

from typing import Any, cast

from glio_proteogen.contracts.m20_01 import (
    M2001_OUTPUT_MEDIA_TYPE,
    M2001_PROVISIONAL_ABI,
    CompatibilityRule,
    UpstreamSourceKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 9


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
        claim="Caller-declared compatibility evidence.",
    )


def test_provisional_schemas_preserve_typed_resolution_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(
        cast("str", schema["$schema"]).endswith("2020-12/schema") for schema in schemas.values()
    )
    assert all(_metadata(schema)["provisionalAbi"] for schema in schemas.values())
    assert all(_metadata(schema)["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        _metadata(schema)["typedDiscoveryRequired"]
        and _metadata(schema)["versionCompatibilityRequired"]
        and _metadata(schema)["consentRequired"]
        and _metadata(schema)["intendedUseRequired"]
        and _metadata(schema)["supportRequired"]
        and _metadata(schema)["provenancePreserved"]
        and _metadata(schema)["typedRejectionsRequired"]
        and _metadata(schema)["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        _metadata(schema)["parentTarget"] == "protein subtype" for schema in schemas.values()
    )
    assert _metadata(schemas["output"])["outputMediaType"] == M2001_OUTPUT_MEDIA_TYPE
    assert M2001_PROVISIONAL_ABI is True


def test_compatibility_rule_keeps_required_source_and_intended_use_typed() -> None:
    rule = CompatibilityRule(
        rule_id="rule-1",
        name="Biomarker-panel translation compatibility",
        required_source_kind=UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME,
        required_media_type="application/vnd.glio-proteogen.source+json",
        required_intended_use="protein subtype export",
        evidence=(_evidence(),),
    )
    assert rule.required_source_kind is UpstreamSourceKind.MASS_SPECTROMETRY_PROTEOME
    assert rule.required_intended_use == "protein subtype export"
