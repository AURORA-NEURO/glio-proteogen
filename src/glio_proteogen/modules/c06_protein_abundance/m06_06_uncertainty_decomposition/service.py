"""Stateless application boundary for provisional M06-06."""

from glio_proteogen.contracts.m06_06 import (
    DecomposeProteinAbundanceUncertaintyRequest,
    ProteinAbundanceUncertaintyDecompositionResult,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition.engine import (
    M0606UncertaintyDecompositionEngine,
    _validate_typed_request,
)


class M0606Service:
    """Authorize, strictly validate, and execute one M06-06 request."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M0606UncertaintyDecompositionEngine | None = None,
    ) -> None:
        self._engine = engine or M0606UncertaintyDecompositionEngine()

    @staticmethod
    def validate_request(request: object) -> DecomposeProteinAbundanceUncertaintyRequest:
        return _validate_typed_request(request)

    def _execute_validated(
        self,
        request: DecomposeProteinAbundanceUncertaintyRequest,
    ) -> ProteinAbundanceUncertaintyDecompositionResult:
        return self._engine.decompose_validated(request)

    def execute(self, request: object) -> ProteinAbundanceUncertaintyDecompositionResult:
        return self._execute_validated(self.validate_request(request))


__all__ = ["M0606Service"]
