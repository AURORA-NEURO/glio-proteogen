"""Strict plugin seam for M19-04 intended-use adaptation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1904Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_04 import (
        AdaptProteotypeIntendedUseRequest,
        ProteotypeIntendedUseAdapterResult,
    )


@dataclass(frozen=True, slots=True)
class M1904PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-04"
    operation: str = "adapt_proteotype_intended_use"
    output_media_type: str = "application/vnd.glio-proteogen.m19-04+json"
    parent_target: str = "proteotype"
    owner: str = "Clinical science"
    safety_class: str = "S2"
    gate: str = "G3"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    intended_use_registration: bool = True
    explicit_abstention: bool = True


class M1904Plugin:
    """Expose only strict validate, run and replay operations."""

    descriptor: Final = M1904PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1904Engine()

    def validate_request(self, candidate: object) -> AdaptProteotypeIntendedUseRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: AdaptProteotypeIntendedUseRequest,
    ) -> ProteotypeIntendedUseAdapterResult:
        return self._engine.adapt(request)

    def replay(
        self,
        result: ProteotypeIntendedUseAdapterResult,
    ) -> ProteotypeIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M1904Plugin", "M1904PluginDescriptor"]
