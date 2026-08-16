"""Sealed plugin descriptor and capability boundary for M16-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1606Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m16_06 import (
        AdjudicateProteinRnaDiscordanceQueueRequest,
        ProteinRnaDiscordanceAdjudicationResult,
    )


@dataclass(frozen=True, slots=True)
class M1606PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M16-06"
    operation: str = "adjudicate_protein_rna_discordance_queue"
    output_media_type: str = "application/vnd.glio-proteogen.m16-06+json"
    parent_target: str = "protein-RNA discordance"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    immutable_history: bool = True
    blinded_review: bool = True


class M1606Plugin:
    """Only exposes typed request validation, adjudication, and replay."""

    descriptor: Final = M1606PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1606Engine()

    def validate_request(self, candidate: object) -> AdjudicateProteinRnaDiscordanceQueueRequest:
        return self._engine.validate_request(candidate)

    def run(
        self, request: AdjudicateProteinRnaDiscordanceQueueRequest
    ) -> ProteinRnaDiscordanceAdjudicationResult:
        return self._engine.adjudicate(request)

    def replay(
        self, result: ProteinRnaDiscordanceAdjudicationResult
    ) -> ProteinRnaDiscordanceAdjudicationResult:
        return self._engine.replay(result)


__all__ = ["M1606Plugin", "M1606PluginDescriptor"]
