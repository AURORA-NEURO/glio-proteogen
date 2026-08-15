"""Focused schema and automation-bias smoke for provisional M20-05."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m20_05 import (
    M2005_M2004_RESULT_MEDIA_TYPE,
    M2005_OUTPUT_MEDIA_TYPE,
    M2005_PROVISIONAL_ABI,
    OrderingPolicy,
    ReviewItem,
    ReviewItemStatus,
    ViewKind,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8
_SOURCE_ARTIFACT = {
    "artifact_id": "source-1",
    "version": "1.0.0",
    "digest": "sha256:" + "a" * 64,
    "media_type": "application/json",
}
_EVIDENCE = {
    "reference": _SOURCE_ARTIFACT,
    "role": "evidence",
    "claim": "Review evidence is retained.",
}


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
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["safeDefaultOrderingRequired"] is True
        assert metadata["automationBiasGuardRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "protein subtype"
        assert metadata["upstreamInputMediaType"] == M2005_M2004_RESULT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2005_OUTPUT_MEDIA_TYPE
    assert M2005_PROVISIONAL_ABI is True


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
