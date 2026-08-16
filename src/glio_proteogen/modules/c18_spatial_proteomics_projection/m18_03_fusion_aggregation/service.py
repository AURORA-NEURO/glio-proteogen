"""M18-03 fusion and aggregation service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1803Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_03 import (
        BiomarkerPanelIntegratedEvidenceResult,
        FuseBiomarkerPanelEvidenceRequest,
    )


class M1803Service:
    """Stateless service wrapper for component-specific fusion."""

    def __init__(self) -> None:
        self._engine = M1803Engine()

    def validate_request(self, candidate: object) -> FuseBiomarkerPanelEvidenceRequest:
        return self._engine.validate_request(candidate)

    def fuse(self, candidate: object) -> BiomarkerPanelIntegratedEvidenceResult:
        return self._engine.adapt(candidate)

    def replay(
        self,
        result: BiomarkerPanelIntegratedEvidenceResult,
    ) -> BiomarkerPanelIntegratedEvidenceResult:
        return self._engine.replay(result)


__all__ = ["M1803Service"]
