"""Runtime and replay tests for M20-05 workflow presentation."""

from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m20_05 import (
    OrderingPolicy,
    ReviewItemStatus,
    ViewKind,
    WorkspaceStatus,
)
from glio_proteogen.contracts.m20_05.canonical import result_payload_digest
from glio_proteogen.kernel.models import Limitation
from glio_proteogen.modules.c20_biomarker_panel.m20_05_workflow_presentation_service import (
    M2005AuthorizationError,
    M2005ReplayError,
    M2005Service,
    preflight_m2005_authorization,
)
from tests.contract.test_m20_05_adversarial import _item, _request


def test_service_presents_exact_workspace_and_replays() -> None:
    request = _request()
    service = M2005Service()
    result = service.present(request)
    assert result.status is WorkspaceStatus.PRESENTED
    assert result.workspace is not None
    assert tuple(item.view_kind for item in result.workspace.items) == (
        ViewKind.DISCREPANCY,
        ViewKind.UNCERTAINTY,
        ViewKind.EVIDENCE_REVIEW,
        ViewKind.PROVENANCE,
        ViewKind.NEXT_ACTION,
        ViewKind.TASK_SUMMARY,
    )
    assert result.workspace.ordering is request.policy.default_ordering
    assert result.support_decision.status.value == "supported"
    assert service.replay(result) == result


def test_uncertainty_first_policy_changes_output_order_deterministically() -> None:
    base = _request()
    request = base.model_copy(
        update={
            "policy": base.policy.model_copy(
                update={"default_ordering": OrderingPolicy.UNCERTAINTY_FIRST}
            )
        }
    )
    result = M2005Service().present(request)

    assert result.workspace is not None
    assert tuple(item.view_kind for item in result.workspace.items) == (
        ViewKind.DISCREPANCY,
        ViewKind.UNCERTAINTY,
        ViewKind.EVIDENCE_REVIEW,
        ViewKind.PROVENANCE,
        ViewKind.NEXT_ACTION,
        ViewKind.TASK_SUMMARY,
    )
    assert tuple(item.position for item in result.workspace.items) == tuple(range(6))


def test_safe_default_prioritizes_limited_review_before_supported_views() -> None:
    base = _request()
    limited = _item(ViewKind.TASK_SUMMARY, 0, status=ReviewItemStatus.LIMITED)
    request = base.model_copy(update={"review_items": (limited, *base.review_items[1:])})

    result = M2005Service().present(request)

    assert result.workspace is not None
    assert result.workspace.items[0].view_kind is ViewKind.TASK_SUMMARY
    assert result.workspace.items[0].status is ReviewItemStatus.LIMITED


def test_abstained_item_emits_safe_abstention_without_workspace() -> None:
    request = _request()
    abstained = _item(
        request.review_items[0].view_kind,
        0,
        status=ReviewItemStatus.ABSTAINED,
    )
    request = request.model_copy(update={"review_items": (abstained, *request.review_items[1:])})
    result = M2005Service().present(request)
    assert result.status is WorkspaceStatus.ABSTAINED
    assert result.workspace is None
    assert result.support_decision.status.value == "review_required"
    assert result.abstention_reason is not None
    assert result.findings


def test_denied_control_fails_closed_before_presentation() -> None:
    request = _request()
    denied_support = request.context.references.support.model_copy(update={"state": "rejected"})
    context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(update={"support": denied_support})
        }
    )
    with pytest.raises(M2005AuthorizationError):
        M2005Service().present(request.model_copy(update={"context": context}))


def test_preflight_rejects_malformed_control_mapping() -> None:
    with pytest.raises(M2005AuthorizationError):
        preflight_m2005_authorization({"context": {"references": {}}})
    with pytest.raises(M2005AuthorizationError):
        preflight_m2005_authorization(object())


def test_replay_rejects_tampered_request_or_result_digest() -> None:
    service = M2005Service()
    result = service.present(_request())
    with pytest.raises(M2005ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    with pytest.raises((M2005ReplayError, ValidationError)):
        service.replay(
            result.model_copy(
                update={
                    "request_digest": "sha256:" + "e" * 64,
                    "result_digest": result.result_digest,
                }
            )
        )


def test_replay_rejects_self_rehashed_semantic_mutation() -> None:
    service = M2005Service()
    result = service.present(_request())
    mutated = result.model_copy(
        update={
            "limitations": (
                *result.limitations,
                Limitation(code="forged", statement="forged semantic state"),
            )
        }
    )
    mutated = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
    with pytest.raises(M2005ReplayError, match="semantic replay"):
        service.replay(mutated)


def test_service_requires_typed_request() -> None:
    with pytest.raises((TypeError, ValidationError, ValueError)):
        M2005Service().present(cast("Any", {"request_id": "not-a-request"}))
