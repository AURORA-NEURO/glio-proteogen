"""M20-05 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M2005Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_05 import (
        PresentProteinSubtypeHumanReviewWorkspaceRequest,
        ProteinSubtypeHumanReviewWorkspaceResult,
    )


class M2005Service:
    """Stateless service wrapper for workflow presentation and replay."""

    def __init__(self) -> None:
        self._engine = M2005Engine()

    def validate_request(
        self, candidate: object
    ) -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
        return self._engine.validate_request(candidate)

    def present(self, candidate: object) -> ProteinSubtypeHumanReviewWorkspaceResult:
        return self._engine.present(candidate)

    def replay(
        self,
        result: ProteinSubtypeHumanReviewWorkspaceResult,
    ) -> ProteinSubtypeHumanReviewWorkspaceResult:
        return self._engine.replay(result)


__all__ = ["M2005Service"]
