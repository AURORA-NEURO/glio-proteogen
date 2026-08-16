"""Stateless application seam for provisional M07-01."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import (
    BuiltFormalStateResult,
    FormalStateAuthorizationError,
    FormalStateInputError,
    M0701FormalStateEngine,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m07_01 import (
        ValidateCopyNumberStateRequest,
        ValidateCopyNumberStateResult,
    )


class M0701Service:
    """Validate, execute, and replay one formal-state request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0701FormalStateEngine | None = None) -> None:
        self._engine = engine or M0701FormalStateEngine()

    @staticmethod
    def validate_request(request: object) -> ValidateCopyNumberStateRequest:
        return M0701FormalStateEngine.validate_request(request)

    def execute(self, request: object) -> BuiltFormalStateResult:
        return self._engine.execute(request)

    def validate(self, request: object) -> BuiltFormalStateResult:
        return self._engine.validate(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ValidateCopyNumberStateResult:
        return self._engine.verify(result, canonical_bytes)


__all__ = [
    "BuiltFormalStateResult",
    "FormalStateAuthorizationError",
    "FormalStateInputError",
    "M0701Service",
]
