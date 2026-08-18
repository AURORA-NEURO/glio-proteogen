"""Focused contract/schema smoke for provisional M19-04."""

from typing import cast

from glio_proteogen.contracts.m19_04 import (
    M1904_OUTPUT_MEDIA_TYPE,
    M1904_PROHIBITED_CLAIM_TERMS,
    M1904_PROVISIONAL_ABI,
    ClaimCeiling,
    DisplaySemantics,
    IntendedUseKind,
    IntendedUseRegistration,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 8


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", schema["x-glio-contract"])


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
    assert all(str(schema["$schema"]).endswith("2020-12/schema") for schema in schemas.values())
    assert all(_metadata(schema)["provisionalAbi"] for schema in schemas.values())
    assert all(_metadata(schema)["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        _metadata(schema)["intendedUseRegistrationRequired"]
        and _metadata(schema)["evidenceTierRequired"]
        and _metadata(schema)["claimCeilingRequired"]
        and _metadata(schema)["displaySemanticsRequired"]
        and _metadata(schema)["policyDecisionRequired"]
        and _metadata(schema)["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        str(_metadata(schema)["upstreamInputMediaType"]).endswith("m19-03+json")
        and _metadata(schema)["parentTarget"] == "proteotype"
        for schema in schemas.values()
    )
    assert _metadata(schemas["output"])["outputMediaType"] == M1904_OUTPUT_MEDIA_TYPE
    assert M1904_PROVISIONAL_ABI is True
    assert all(
        tuple(cast("list[str]", item["prohibitedClaimTerms"])) == M1904_PROHIBITED_CLAIM_TERMS
        for item in (_metadata(schema) for schema in schemas.values())
    )


def test_registration_keeps_claim_ceiling_and_display_semantics_typed() -> None:
    evidence = (_evidence(),)
    registration = IntendedUseRegistration(
        registration_id="registration-1",
        version="0.1.0",
        intended_use=IntendedUseKind.CLINICAL_REVIEW,
        audience="Clinical science reviewer",
        evidence_tier=2,
        claim_ceiling=ClaimCeiling(
            maximum_claim="Descriptive proteotype state.",
            prohibited_interpretations=("Treatment recommendation",),
            rationale="Evidence tier bounds interpretation.",
            evidence=evidence,
        ),
        display_semantics=DisplaySemantics(
            section_order=("support", "uncertainty", "limitations"),
            safe_default="Show bounded clinical-review context.",
            evidence=evidence,
        ),
        evidence=evidence,
    )
    assert registration.intended_use is IntendedUseKind.CLINICAL_REVIEW
    assert registration.display_semantics.show_uncertainty is True
