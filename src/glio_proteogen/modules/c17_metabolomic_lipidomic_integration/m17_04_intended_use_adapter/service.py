"""M17-04 intended-use adapter service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1704Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m17_04 import (
        AdaptVariantPeptideIntendedUseRequest,
        VariantPeptideIntendedUseAdapterResult,
    )


class M1704Service:
    """Stateless service wrapper for intended-use policy adaptation."""

    def __init__(self) -> None:
        self._engine = M1704Engine()

    def validate_request(self, candidate: object) -> AdaptVariantPeptideIntendedUseRequest:
        return self._engine.validate_request(candidate)

    def adapt(self, candidate: object) -> VariantPeptideIntendedUseAdapterResult:
        return self._engine.adapt(candidate)

    def replay(
        self,
        result: VariantPeptideIntendedUseAdapterResult,
    ) -> VariantPeptideIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M1704Service"]
