"""Adversarial contract and safety-closure tests for M16-05."""

# ruff: noqa: E501

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m16_05 import (
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
from tests.modules.c16_kinophos_object_consumer.test_m16_05_engine import _request


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
