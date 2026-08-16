"""M20-03 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2003Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_03 import (
        FuseProteinSubtypeEvidenceRequest,
        ProteinSubtypeIntegratedEvidenceResult,
    )


class M2003Service:
    """Stateless service wrapper for component-specific fusion."""

    def __init__(self) -> None:
        self._engine = M2003Engine()

    def validate_request(self, candidate: object) -> FuseProteinSubtypeEvidenceRequest:
        return self._engine.validate_request(candidate)

    def fuse(self, candidate: object) -> ProteinSubtypeIntegratedEvidenceResult:
        return self._engine.fuse(candidate)

    def replay(
        self,
        result: ProteinSubtypeIntegratedEvidenceResult,
    ) -> ProteinSubtypeIntegratedEvidenceResult:
        return self._engine.replay(result)


__all__ = ["M2003Service"]
