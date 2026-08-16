"""Focused contract/schema smoke for provisional M18-05."""

import pytest

from glio_proteogen.contracts.m18_05 import (
    M1805_OUTPUT_MEDIA_TYPE,
    M1805_PROVISIONAL_ABI,
    WorkspaceFindingCode,
    WorkspaceSectionKind,
    WorkspaceStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 6


def test_provisional_schemas_require_human_review_views() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["taskViewsRequired"]
        and schema["x-glio-contract"]["evidenceSummaryRequired"]
        and schema["x-glio-contract"]["uncertaintyVisible"]
        and schema["x-glio-contract"]["discrepanciesVisible"]
        and schema["x-glio-contract"]["provenanceVisible"]
        and schema["x-glio-contract"]["safeDefaultOrderingRequired"]
        and schema["x-glio-contract"]["automationBiasMitigationRequired"]
        and schema["x-glio-contract"]["humanReviewRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["upstreamInputMediaType"].endswith("m18-04+json")
        and schema["x-glio-contract"]["parentTarget"] == "biomarker panel"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1805_OUTPUT_MEDIA_TYPE
    assert M1805_PROVISIONAL_ABI is True


def test_workspace_sections_and_safe_state_are_explicit() -> None:
    assert WorkspaceSectionKind.DISCREPANCIES.value == "discrepancies"
    assert WorkspaceStatus.ABSTAINED.value == "abstained"
    assert WorkspaceFindingCode.AUTOMATION_BIAS_RISK.value == "automation_bias_risk"
    with pytest.raises(AssertionError):
        assert WorkspaceStatus.ABSTAINED is WorkspaceStatus.PRESENTED
