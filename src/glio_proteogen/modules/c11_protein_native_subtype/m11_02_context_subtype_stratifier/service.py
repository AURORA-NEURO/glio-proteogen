"""M11-02 application service boundary."""

from glio_proteogen.contracts.m11_02 import (
    StratifyVariantPeptideContextRequest,
    VariantPeptideContextStratificationResult,
)

from .engine import M1102ContextEngine, _prepare


class M1102Service:
    """Authorize, validate, stratify, and verify one context request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1102ContextEngine | None = None) -> None:
        self._engine = engine or M1102ContextEngine()

    @staticmethod
    def validate_request(request: object) -> StratifyVariantPeptideContextRequest:
        return StratifyVariantPeptideContextRequest.model_validate(_prepare(request), strict=True)

    def _execute_validated(
        self,
        request: StratifyVariantPeptideContextRequest,
    ) -> VariantPeptideContextStratificationResult:
        return self._engine.stratify(request)

    def execute(self, request: object) -> VariantPeptideContextStratificationResult:
        return self._engine.stratify(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideContextStratificationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1102Service"]
