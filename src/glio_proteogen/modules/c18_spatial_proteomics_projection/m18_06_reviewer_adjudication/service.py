"""M18-06 reviewer adjudication service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1806Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_06 import (
        AdjudicateBiomarkerPanelQueueRequest,
        BiomarkerPanelAdjudicationResult,
    )


class M1806Service:
    """Stateless service wrapper for reviewer adjudication."""

    def __init__(self) -> None:
        self._engine = M1806Engine()

    def validate_request(self, candidate: object) -> AdjudicateBiomarkerPanelQueueRequest:
        return self._engine.validate_request(candidate)

    def adjudicate(self, candidate: object) -> BiomarkerPanelAdjudicationResult:
        return self._engine.adapt(candidate)

    def replay(
        self,
        result: BiomarkerPanelAdjudicationResult,
        request: AdjudicateBiomarkerPanelQueueRequest | None = None,
    ) -> BiomarkerPanelAdjudicationResult:
        if request is not None and result.request.model_dump(mode="json") != request.model_dump(
            mode="json"
        ):
            raise ValueError("replay request mismatch")  # noqa: TRY003
        return self._engine.replay(result)


__all__ = ["M1806Service"]
