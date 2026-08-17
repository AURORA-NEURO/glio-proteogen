"""Focused checks for the provisional M05-07 contract spine."""

from datetime import UTC, datetime
from typing import cast

from glio_proteogen.contracts.m05_07 import (
    M0507_M0506_RESULT_MEDIA_TYPE,
    PtmLocalizationDeclaredSupportState,
    PtmLocalizationDimensionSupportDecision,
    PtmLocalizationSupportDimension,
    PtmLocalizationSupportFact,
    PtmLocalizationSupportPolicy,
    PtmLocalizationSupportPrerequisites,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference


def _reference(media_type: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id="result." + "a" * 64,
        version="0.1.0",
        digest="sha256:" + "b" * 64,
        media_type=media_type,
    )


def test_provisional_policy_covers_all_eight_dossier_dimensions() -> None:
    policy = PtmLocalizationSupportPolicy(
        policy_id="policy." + "a" * 64,
        version="0.1.0",
        dimensions=tuple(PtmLocalizationSupportDimension),
        reviewed_by="reviewer." + "b" * 64,
        reviewed_at=datetime.now(UTC),
        evidence=_reference("application/json"),
    )
    assert set(policy.dimensions) == set(PtmLocalizationSupportDimension)


def test_missing_and_unknown_support_cannot_be_supported() -> None:
    fact = PtmLocalizationSupportFact(
        dimension=PtmLocalizationSupportDimension.QUALITY,
        state=PtmLocalizationDeclaredSupportState.UNKNOWN,
        decision=PtmLocalizationDimensionSupportDecision.INDETERMINATE,
        rationale="The upstream quality declaration is unresolved.",
    )
    assert fact.decision is PtmLocalizationDimensionSupportDecision.INDETERMINATE


def test_m05_06_handoff_is_opaque_and_media_type_bound() -> None:
    prerequisites = PtmLocalizationSupportPrerequisites(
        harmonization_result=_reference(M0507_M0506_RESULT_MEDIA_TYPE)
    )
    assert prerequisites.harmonization_result.media_type == M0507_M0506_RESULT_MEDIA_TYPE


def test_schema_exports_mark_the_abi_provisional() -> None:
    schemas = contract_json_schemas()
    assert set(schemas) == {"request", "output", "policy", "prerequisites", "fact", "receipt"}
    assert all(
        cast("dict[str, object]", schema["x-glio-contract"])["provisionalAbi"]
        for schema in schemas.values()
    )
