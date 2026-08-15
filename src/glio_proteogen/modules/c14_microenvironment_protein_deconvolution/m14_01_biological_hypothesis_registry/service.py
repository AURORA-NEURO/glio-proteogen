"""M14-01 service boundary."""

from glio_proteogen.contracts.m14_01 import (
    RegisterProteinSubtypeHypothesesRequest,
    ProteinSubtypeHypothesisRegistryResult,
)

from .engine import M1401HypothesisEngine, _prepare


class M1401Service:
    """Authorize, validate, register, and verify one M14-01 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1401HypothesisEngine | None = None) -> None:
        self._engine = engine or M1401HypothesisEngine()

    @staticmethod
    def validate_request(request: object) -> RegisterProteinSubtypeHypothesesRequest:
        return RegisterProteinSubtypeHypothesesRequest.model_validate(
            _prepare(request), strict=True
        )

    def _execute_validated(
        self,
        request: RegisterProteinSubtypeHypothesesRequest,
    ) -> ProteinSubtypeHypothesisRegistryResult:
        return self._engine.register(request)

    def execute(self, request: object) -> ProteinSubtypeHypothesisRegistryResult:
        return self._engine.register(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeHypothesisRegistryResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1401Service"]


