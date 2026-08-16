"""M13-01 service boundary."""

from glio_proteogen.contracts.m13_01 import (
    ProteotypeHypothesisRegistryResult,
    RegisterProteotypeHypothesesRequest,
)

from .engine import M1301HypothesisEngine, _prepare


class M1301Service:
    """Authorize, validate, register, and verify one M13-01 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1301HypothesisEngine | None = None) -> None:
        self._engine = engine or M1301HypothesisEngine()

    @staticmethod
    def validate_request(request: object) -> RegisterProteotypeHypothesesRequest:
        return RegisterProteotypeHypothesesRequest.model_validate(_prepare(request), strict=True)

    def _execute_validated(
        self,
        request: RegisterProteotypeHypothesesRequest,
    ) -> ProteotypeHypothesisRegistryResult:
        return self._engine.register(request)

    def execute(self, request: object) -> ProteotypeHypothesisRegistryResult:
        return self._engine.register(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeHypothesisRegistryResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1301Service"]
