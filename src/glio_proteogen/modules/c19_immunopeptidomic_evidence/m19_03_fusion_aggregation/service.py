"""M19-03 fusion and aggregation service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1903Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_03 import (
        FuseProteotypeEvidenceRequest,
        ProteotypeIntegratedEvidenceResult,
    )


class M1903Service:
    """Stateless service wrapper for component-specific fusion."""

    def __init__(self) -> None:
        self._engine = M1903Engine()

    def validate_request(self, candidate: object) -> FuseProteotypeEvidenceRequest:
        return self._engine.validate_request(candidate)

    def fuse(self, candidate: object) -> ProteotypeIntegratedEvidenceResult:
        return self._engine.adapt(candidate)

    def replay(
        self,
        result: ProteotypeIntegratedEvidenceResult,
        request: FuseProteotypeEvidenceRequest | None = None,
    ) -> ProteotypeIntegratedEvidenceResult:
        if request is not None and result.request.model_dump(mode="json") != request.model_dump(
            mode="json"
        ):
            raise ValueError from None
        return self._engine.replay(result)


__all__ = ["M1903Service"]
