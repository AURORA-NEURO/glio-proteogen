"""Sealed M20-05 plugin descriptor and validated request seam."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M2005Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_05 import (
        PresentProteinSubtypeHumanReviewWorkspaceRequest,
        ProteinSubtypeHumanReviewWorkspaceResult,
    )


@dataclass(frozen=True, slots=True)
class M2005PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M20-05"
    operation: str = "present_protein_subtype_human_review_workspace"
    output_media_type: str = "application/vnd.glio-proteogen.m20-05+json"
    upstream_media_type: str = "application/vnd.glio-proteogen.m20-04+json"
    parent_target: str = "protein subtype"
    owner: str = "Platform engineering"
    safety_class: str = "S2"
    gate: str = "G4"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    explicit_abstention: bool = True
    task_specific_views_required: bool = True
    evidence_summary_required: bool = True
    uncertainty_required: bool = True
    discrepancy_review_required: bool = True
    provenance_required: bool = True
    automation_bias_guard_required: bool = True


class M2005Plugin:
    """Expose only typed presentation and exact replay."""

    descriptor: Final = M2005PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M2005Engine()

    def validate_request(
        self, candidate: object
    ) -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: PresentProteinSubtypeHumanReviewWorkspaceRequest,
    ) -> ProteinSubtypeHumanReviewWorkspaceResult:
        return self._engine.present(request)

    def replay(
        self,
        result: ProteinSubtypeHumanReviewWorkspaceResult,
    ) -> ProteinSubtypeHumanReviewWorkspaceResult:
        return self._engine.replay(result)


__all__ = ["M2005Plugin", "M2005PluginDescriptor"]
