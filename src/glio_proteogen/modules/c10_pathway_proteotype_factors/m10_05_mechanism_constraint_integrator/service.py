"""Service boundary for M10-05."""

from glio_proteogen.contracts.m10_05 import (
    IntegrateProteinRnaConstraintsRequest,
    ProteinRnaConstraintIntegrationResult,
)

from .engine import M1005ConstraintEngine, _prepare


class M1005Service:
    """Authorize, validate, integrate, and verify one M10-05 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1005ConstraintEngine | None = None) -> None:
        self._engine = engine or M1005ConstraintEngine()

    @staticmethod
    def validate_request(request: object) -> IntegrateProteinRnaConstraintsRequest:
        return IntegrateProteinRnaConstraintsRequest.model_validate(_prepare(request), strict=True)

    def _execute_validated(
        self,
        request: IntegrateProteinRnaConstraintsRequest,
    ) -> ProteinRnaConstraintIntegrationResult:
        return self._engine.integrate(request)

    def execute(self, request: object) -> ProteinRnaConstraintIntegrationResult:
        return self._engine.integrate(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaConstraintIntegrationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1005Service"]
