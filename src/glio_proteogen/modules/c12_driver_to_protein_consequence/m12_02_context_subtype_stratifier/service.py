"""M12-02 service boundary."""

from glio_proteogen.contracts.m12_02 import (
    BiomarkerPanelContextStratificationResult,
    StratifyBiomarkerPanelContextRequest,
)

from .engine import M1202ContextEngine, preflight_context_authorization


class M1202Service:
    """Authorize, strictly validate, stratify, and verify one M12-02 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1202ContextEngine | None = None) -> None:
        self._engine = engine or M1202ContextEngine()

    @staticmethod
    def validate_request(request: object) -> StratifyBiomarkerPanelContextRequest:
        preflight_context_authorization(request)
        return StratifyBiomarkerPanelContextRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: StratifyBiomarkerPanelContextRequest,
    ) -> BiomarkerPanelContextStratificationResult:
        return self._engine.stratify(request)

    def execute(self, request: object) -> BiomarkerPanelContextStratificationResult:
        return self._engine.stratify(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelContextStratificationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1202Service"]
