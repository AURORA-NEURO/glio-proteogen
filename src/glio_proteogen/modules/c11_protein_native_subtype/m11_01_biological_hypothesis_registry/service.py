"""M11-01 service boundary."""

from glio_proteogen.contracts.m11_01 import (
    RegisterVariantPeptideHypothesesRequest,
    VariantPeptideHypothesisRegistryResult,
)

from .engine import M1101HypothesisEngine, _prepare


class M1101Service:
    """Authorize, validate, register, and verify one M11-01 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1101HypothesisEngine | None = None) -> None:
        self._engine = engine or M1101HypothesisEngine()

    @staticmethod
    def validate_request(request: object) -> RegisterVariantPeptideHypothesesRequest:
        return RegisterVariantPeptideHypothesesRequest.model_validate(
            _prepare(request), strict=True
        )

    def _execute_validated(
        self,
        request: RegisterVariantPeptideHypothesesRequest,
    ) -> VariantPeptideHypothesisRegistryResult:
        return self._engine.register(request)

    def execute(self, request: object) -> VariantPeptideHypothesisRegistryResult:
        return self._engine.register(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideHypothesisRegistryResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1101Service"]
