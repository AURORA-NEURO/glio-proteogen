"""Lightweight contract and schema gates for provisional M16-05."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m16_05 import (
    M1605_OUTPUT_MEDIA_TYPE,
    HumanReviewWorkspace,
    WorkspaceConfiguration,
    WorkspaceItem,
    WorkspaceItemStatus,
    WorkspaceView,
    WorkspaceViewKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_COUNT = 7


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1605": label}),
        media_type="application/json",
    )


def test_m1605_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1605_OUTPUT_MEDIA_TYPE
    assert metadata["parentTarget"] == "protein_rna_discordance"
    assert metadata["safeDefaultOrderingRequired"]
    assert metadata["automationBiasControls"]
    assert metadata["discrepanciesVisible"]
    assert metadata["nextActionVisible"]


def test_m1605_workspace_requires_safe_default_ordering() -> None:
    item = WorkspaceItem(
        item_id="item.task",
        title="Task summary",
        summary="Review the aligned evidence.",
        kind=WorkspaceViewKind.TASK,
        status=WorkspaceItemStatus.AVAILABLE,
        priority=1,
        next_action="Confirm the evidence scope.",
        source_artifacts=(_artifact("task"),),
    )

    def view(kind: WorkspaceViewKind) -> WorkspaceView:
        view_item = item.model_copy(
            update={
                "item_id": f"item.{kind.value}",
                "kind": kind,
                "title": kind.value.title(),
            }
        )
        return WorkspaceView(
            view_id=f"view.{kind.value}",
            kind=kind,
            title=kind.value.title(),
            purpose="Orient the reviewer.",
            items=(view_item,),
            default_item_order=(view_item.item_id,),
        )

    views = tuple(view(kind) for kind in WorkspaceViewKind)
    kinds = tuple(WorkspaceViewKind)
    workspace = HumanReviewWorkspace(
        workspace_id="workspace.review",
        version="1.0.0",
        views=views,
        configuration=WorkspaceConfiguration(
            configuration_id="config.review",
            version="1.0.0",
            default_view_order=kinds,
            visible_sections=kinds,
        ),
    )
    assert workspace.views[0].default_item_order == ("item.task",)

    with pytest.raises(ValueError, match="default item order"):
        WorkspaceView(
            view_id="view.invalid",
            kind=WorkspaceViewKind.TASK,
            title="Invalid",
            purpose="Missing ordering.",
            items=(item,),
            default_item_order=("item.other",),
        )
