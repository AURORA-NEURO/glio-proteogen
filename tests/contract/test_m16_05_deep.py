"""Adversarial contract and safety-closure tests for M16-05."""

# ruff: noqa: E501

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m16_05 import (
    M1605_M1604_INPUT_MEDIA_TYPE,
    ProteinRnaDiscordanceReviewWorkspaceResult,
    WorkspaceConfiguration,
    WorkspaceFindingCode,
    WorkspacePresentationStatus,
    WorkspaceViewKind,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_05_workflow_presentation_service import (
    M1605PresentationEngine,
)
from tests.modules.c16_kinophos_object_consumer.test_m16_05_engine import _artifact, _request


def test_workspace_configuration_rejects_duplicate_or_missing_safe_views() -> None:
    kinds = tuple(WorkspaceViewKind)
    with pytest.raises(ValidationError, match="default view order must be unique"):
        WorkspaceConfiguration(
            configuration_id="configuration.duplicate",
            version="1.0.0",
            default_view_order=(*kinds, WorkspaceViewKind.TASK),
            visible_sections=kinds,
        )
    with pytest.raises(ValidationError, match="every required workspace view"):
        WorkspaceConfiguration(
            configuration_id="configuration.missing",
            version="1.0.0",
            default_view_order=kinds[:-1],
            visible_sections=kinds,
        )
    with pytest.raises(ValidationError, match="visible sections must be unique"):
        WorkspaceConfiguration(
            configuration_id="configuration.visible-duplicate",
            version="1.0.0",
            default_view_order=kinds,
            visible_sections=(*kinds, WorkspaceViewKind.TASK),
        )


def test_result_closure_rejects_wrong_identity_evidence_and_duplicate_findings() -> None:
    result = M1605PresentationEngine().present(_request())
    with pytest.raises(ValidationError, match="identifier must be derived"):
        ProteinRnaDiscordanceReviewWorkspaceResult.model_validate(
            result.model_dump(mode="python") | {"result_id": "result.wrong"}
        )
    with pytest.raises(ValidationError, match="requires evidence"):
        ProteinRnaDiscordanceReviewWorkspaceResult.model_validate(
            result.model_dump(mode="python") | {"evidence": ()}
        )
    with pytest.raises(ValidationError, match="finding codes must be unique"):
        ProteinRnaDiscordanceReviewWorkspaceResult.model_validate(
            result.model_dump(mode="python")
            | {
                "findings": (
                    WorkspaceFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    WorkspaceFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                )
            }
        )
    with pytest.raises(ValidationError, match="result digest does not match"):
        ProteinRnaDiscordanceReviewWorkspaceResult.model_validate(
            result.model_dump(mode="python") | {"result_digest": sha256_digest("tampered")}
        )


def test_result_status_closure_rejects_presented_review_and_abstained_mutations() -> None:
    result = M1605PresentationEngine().present(_request())
    with pytest.raises(ValidationError, match="presented workspace requires"):
        ProteinRnaDiscordanceReviewWorkspaceResult.model_validate(
            result.model_dump(mode="python") | {"human_review_required": True}
        )


def test_workspace_and_request_identity_closure_rejects_duplicates_and_wrong_upstream() -> None:
    result = M1605PresentationEngine().present(_request())
    assert result.workspace is not None
    view = result.workspace.views[0]
    item = view.items[0]
    with pytest.raises(ValidationError, match="workspace item ids must be unique"):
        type(view).model_validate(view.model_dump(mode="python") | {"items": (item, item)})
    with pytest.raises(ValidationError, match="workspace view ids must be unique"):
        type(result.workspace).model_validate(
            result.workspace.model_dump(mode="python")
            | {
                "views": (
                    result.workspace.views[0],
                    result.workspace.views[0],
                    *result.workspace.views[2:],
                )
            }
        )
    with pytest.raises(ValidationError, match="every required view kind"):
        type(result.workspace).model_validate(
            result.workspace.model_dump(mode="python") | {"views": result.workspace.views[:-1]}
        )
    request = _request()
    with pytest.raises(ValidationError, match="bind the provisional M16-04"):
        type(request).model_validate(
            request.model_dump(mode="python")
            | {
                "upstream_result": _artifact(
                    "wrong", M1605_M1604_INPUT_MEDIA_TYPE.replace("m16-04", "m16-03")
                )
            }
        )
    with pytest.raises(ValidationError, match="source artifact references"):
        type(request).model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (*request.source_artifacts, request.source_artifacts[0])}
        )
    review = M1605PresentationEngine().present(_request(label="warning"))
    with pytest.raises(ValidationError, match="review workspace requires"):
        ProteinRnaDiscordanceReviewWorkspaceResult.model_validate(
            review.model_dump(mode="python") | {"human_review_required": False}
        )
    with pytest.raises(ValidationError, match="abstained result requires"):
        ProteinRnaDiscordanceReviewWorkspaceResult.model_validate(
            result.model_dump(mode="python")
            | {
                "status": WorkspacePresentationStatus.ABSTAINED,
                "workspace": None,
                "abstention_reason": None,
            }
        )
