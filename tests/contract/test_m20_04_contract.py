"""Focused contract/schema smoke for provisional M20-04."""

from glio_proteogen.contracts.m20_04 import (
    M2004_OUTPUT_MEDIA_TYPE,
    M2004_PROVISIONAL_ABI,
    ClaimCeiling,
    DisplaySemantics,
    IntendedUseKind,
    IntendedUseRegistration,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

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
        claim="Caller-declared intended-use evidence.",
    )


def test_provisional_schemas_preserve_intended_use_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["intendedUseRegistrationRequired"]
        and schema["x-glio-contract"]["evidenceTierRequired"]
        and schema["x-glio-contract"]["claimCeilingRequired"]
        and schema["x-glio-contract"]["displaySemanticsRequired"]
        and schema["x-glio-contract"]["policyDecisionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m20-03+json")
        and schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2004_OUTPUT_MEDIA_TYPE
    assert M2004_PROVISIONAL_ABI is True


def test_registration_keeps_claim_ceiling_and_display_semantics_typed() -> None:
    evidence = (_evidence(),)
    registration = IntendedUseRegistration(
        registration_id="registration-1",
        version="0.1.0",
        intended_use=IntendedUseKind.INTERNAL_VALIDATION,
        audience="Data engineering reviewer",
        evidence_tier=2,
        claim_ceiling=ClaimCeiling(
            maximum_claim="Descriptive protein subtype state.",
            prohibited_interpretations=("Treatment recommendation",),
            rationale="Evidence tier bounds interpretation.",
            evidence=evidence,
        ),
        display_semantics=DisplaySemantics(
            section_order=("support", "uncertainty", "limitations"),
            safe_default="Show bounded internal-validation context.",
            evidence=evidence,
        ),
        evidence=evidence,
    )
    assert registration.intended_use is IntendedUseKind.INTERNAL_VALIDATION
    assert registration.display_semantics.show_uncertainty is True
