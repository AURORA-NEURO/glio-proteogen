"""Sealed M18-06 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1806Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_06 import (
        AdjudicateBiomarkerPanelQueueRequest,
        BiomarkerPanelAdjudicationResult,
    )


@dataclass(frozen=True, slots=True)
class M1806PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M18-06"
    operation: str = "adjudicate_biomarker_panel_discrepancy_queue"
    output_media_type: str = "application/vnd.glio-proteogen.m18-06+json"
    parent_target: str = "biomarker panel"
    owner: str = "Data engineering"
    safety_class: str = "S2"
    evidence_gate: str = "G4"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    blinded_review: bool = True
    immutable_history: bool = True
    explicit_abstention: bool = True


class M1806Plugin:
    """Expose only bounded adjudication and exact replay."""

    descriptor: Final = M1806PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1806Engine()

    def validate_request(self, candidate: object) -> AdjudicateBiomarkerPanelQueueRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: AdjudicateBiomarkerPanelQueueRequest,
    ) -> BiomarkerPanelAdjudicationResult:
        return self._engine.adapt(request)

    def replay(
        self,
        result: BiomarkerPanelAdjudicationResult,
    ) -> BiomarkerPanelAdjudicationResult:
        return self._engine.replay(result)


__all__ = ["M1806Plugin", "M1806PluginDescriptor"]
