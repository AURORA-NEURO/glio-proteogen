"""Focused schema and automation-bias smoke for provisional M19-05."""

from typing import Any, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from glio_proteogen.contracts.m19_05 import (
    M1905_DOSSIER_SHA256,
    M1905_DOSSIER_SLICE,
    M1905_M1904_RESULT_MEDIA_TYPE,
    M1905_OUTPUT_MEDIA_TYPE,
    M1905_PROHIBITED_CLAIM_TERMS,
    M1905_PROVISIONAL_ABI,
    OrderingPolicy,
    ReviewItem,
    ReviewItemStatus,
    ViewKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 8
_SOURCE_ARTIFACT = ArtifactReference(
    artifact_id="source-1",
    version="1.0.0",
    digest="sha256:" + "a" * 64,
    media_type="application/json",
)
_EVIDENCE = EvidenceReference(
    reference=_SOURCE_ARTIFACT,
    role="evidence",
    claim="Review evidence is retained.",
)


def test_provisional_schemas_require_safe_review_workspace_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "review-item",
        "next-action",
        "workspace",
        "configuration",
        "policy",
        "finding",
    )
    for schema_value in schemas.values():
        schema = cast("dict[str, Any]", schema_value)
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, Any]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["dossierSha256"] == M1905_DOSSIER_SHA256
        assert metadata["dossierSlice"] == M1905_DOSSIER_SLICE
        assert metadata["safeDefaultOrderingRequired"] is True
        assert metadata["automationBiasGuardRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "proteotype"
        assert metadata["upstreamInputMediaType"] == M1905_M1904_RESULT_MEDIA_TYPE
        assert tuple(cast("list[str]", metadata["prohibitedClaimTerms"])) == (
            *M1905_PROHIBITED_CLAIM_TERMS,
        )
    output_schema = cast("dict[str, Any]", schemas["output"])
    output_metadata = cast("dict[str, Any]", output_schema["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M1905_OUTPUT_MEDIA_TYPE
    assert M1905_PROVISIONAL_ABI is True


def test_review_item_contains_evidence_uncertainty_and_provenance() -> None:
    item = ReviewItem(
        item_id="item-1",
        view_kind=ViewKind.EVIDENCE_REVIEW,
        title="Evidence review",
        position=0,
        status=ReviewItemStatus.LIMITED,
        evidence_summary="Support is limited.",
        uncertainty_summary="Sampling uncertainty remains material.",
        evidence=(_EVIDENCE,),
        provenance_artifact=_SOURCE_ARTIFACT,
    )
    assert item.status is ReviewItemStatus.LIMITED
    assert OrderingPolicy.SAFE_DEFAULT.value == "safe_default"
