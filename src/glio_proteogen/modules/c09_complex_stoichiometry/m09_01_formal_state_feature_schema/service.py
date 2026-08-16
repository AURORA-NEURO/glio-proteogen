"""Single-validation service boundary for M09-01."""

from glio_proteogen.contracts.m09_01 import ValidateComplexActivityStateRequest

from .engine import (
    BuiltM0901Result,
    M0901FormalStateEngine,
    _validate_typed_request,
)


class M0901Service:
    """Validate once, then execute one immutable formal-state request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0901FormalStateEngine | None = None) -> None:
        self._engine = engine or M0901FormalStateEngine()

    @staticmethod
    def validate_request(request: object) -> ValidateComplexActivityStateRequest:
        return _validate_typed_request(request)

    def _execute_validated(
        self,
        request: ValidateComplexActivityStateRequest,
    ) -> BuiltM0901Result:
        return self._engine.validate_validated(request)

    def execute(self, request: object) -> BuiltM0901Result:
        return self._execute_validated(self.validate_request(request))


__all__ = ["M0901Service"]
