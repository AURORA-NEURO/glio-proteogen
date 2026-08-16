"""Sealed M19-06 plugin descriptor and typed entry points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1906Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_06 import (
        AdjudicateProteotypeQueueRequest,
        ProteotypeAdjudicationResult,
    )


@dataclass(frozen=True, slots=True)
class M1906PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-06"
    operation: str = "adjudicate_proteotype_discrepancy_queue"
    output_media_type: str = "application/vnd.glio-proteogen.m19-06+json"
    parent_target: str = "proteotype"
    owner: str = "Platform engineering"
    safety_class: str = "S2"
    evidence_gate: str = "G4"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    blinded_review: bool = True
    immutable_history: bool = True
    explicit_abstention: bool = True


class M1906Plugin:
    """Expose only bounded adjudication and exact replay."""

    descriptor: Final = M1906PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1906Engine()

    def validate_request(self, candidate: object) -> AdjudicateProteotypeQueueRequest:
        return self._engine.validate_request(candidate)

    def run(self, request: AdjudicateProteotypeQueueRequest) -> ProteotypeAdjudicationResult:
        return self._engine.adapt(request)

    def replay(self, result: ProteotypeAdjudicationResult) -> ProteotypeAdjudicationResult:
        return self._engine.replay(result)


__all__ = ["M1906Plugin", "M1906PluginDescriptor"]
