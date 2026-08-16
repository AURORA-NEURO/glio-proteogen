"""Stateless application boundary for provisional M07-06."""

from glio_proteogen.contracts.m07_06 import (
    CopyNumberDosageUncertaintyDecompositionResult,
    DecomposeCopyNumberDosageUncertaintyRequest,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition.engine import (
    M0706UncertaintyDecompositionEngine,
    preflight_m0706_authorization,
)


class M0706Service:
    """Authorize, strictly validate, and execute one M07-06 request."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M0706UncertaintyDecompositionEngine | None = None,
    ) -> None:
        self._engine = engine or M0706UncertaintyDecompositionEngine()

    @staticmethod
    def validate_request(request: object) -> DecomposeCopyNumberDosageUncertaintyRequest:
        preflight_m0706_authorization(request)
        return DecomposeCopyNumberDosageUncertaintyRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: DecomposeCopyNumberDosageUncertaintyRequest,
    ) -> CopyNumberDosageUncertaintyDecompositionResult:
        return self._engine.decompose(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> CopyNumberDosageUncertaintyDecompositionResult:
        """Verify a receipt and optionally replay its immutable request."""

        return self._engine.verify(result, replay=replay)

    def execute(self, request: object) -> CopyNumberDosageUncertaintyDecompositionResult:
        return self._engine.decompose(request)


__all__ = ["M0706Service"]
