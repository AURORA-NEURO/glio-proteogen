"""Service boundary for provisional M16-03 aggregation."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m16_03 import (
    FuseProteinRnaDiscordanceEvidenceRequest,
    ProteinRnaDiscordanceIntegratedEvidenceResult,
)

from .engine import M1603FusionEngine, fuse_protein_rna_discordance_evidence


class _InvalidM1603RequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M16-03 request must be a strict request model or mapping")


class M1603Service:
    """Validate and execute M16-03 through one stateless service object."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M1603FusionEngine()

    def validate_request(self, candidate: object) -> FuseProteinRnaDiscordanceEvidenceRequest:
        if type(candidate) is FuseProteinRnaDiscordanceEvidenceRequest:
            return FuseProteinRnaDiscordanceEvidenceRequest.model_validate(candidate, strict=True)
        if isinstance(candidate, Mapping):
            return FuseProteinRnaDiscordanceEvidenceRequest.model_validate(
                candidate,
                strict=True,
            )
        raise _InvalidM1603RequestError

    def execute(
        self,
        request: FuseProteinRnaDiscordanceEvidenceRequest,
    ) -> ProteinRnaDiscordanceIntegratedEvidenceResult:
        return self._engine.construct(request)

    def construct(self, candidate: object) -> ProteinRnaDiscordanceIntegratedEvidenceResult:
        return fuse_protein_rna_discordance_evidence(candidate)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceIntegratedEvidenceResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1603Service"]
