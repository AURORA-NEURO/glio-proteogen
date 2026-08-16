"""M18-04 typed service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1804Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_04 import (
        AdaptBiomarkerPanelIntendedUseRequest,
        BiomarkerPanelIntendedUseAdapterResult,
    )


class M1804Service:
    def __init__(self) -> None:
        self._engine = M1804Engine()

    def validate_request(self, candidate: object) -> AdaptBiomarkerPanelIntendedUseRequest:
        return self._engine.validate_request(candidate)

    def adapt(self, candidate: object) -> BiomarkerPanelIntendedUseAdapterResult:
        return self._engine.adapt(candidate)

    def replay(
        self,
        result: BiomarkerPanelIntendedUseAdapterResult,
    ) -> BiomarkerPanelIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M1804Service"]
