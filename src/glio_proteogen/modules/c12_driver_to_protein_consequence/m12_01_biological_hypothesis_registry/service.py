"""M12-01 service boundary."""

from glio_proteogen.contracts.m12_01 import (
    BiomarkerPanelHypothesisRegistryResult,
    RegisterBiomarkerPanelHypothesesRequest,
)

from .engine import M1201HypothesisEngine, _prepare


class M1201Service:
    """Authorize, validate, register, and verify one M12-01 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1201HypothesisEngine | None = None) -> None:
        self._engine = engine or M1201HypothesisEngine()

    @staticmethod
    def validate_request(request: object) -> RegisterBiomarkerPanelHypothesesRequest:
        return RegisterBiomarkerPanelHypothesesRequest.model_validate(
            _prepare(request), strict=True
        )

    def _execute_validated(
        self,
        request: RegisterBiomarkerPanelHypothesesRequest,
    ) -> BiomarkerPanelHypothesisRegistryResult:
        return self._engine.register(request)

    def execute(self, request: object) -> BiomarkerPanelHypothesisRegistryResult:
        return self._engine.register(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelHypothesisRegistryResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1201Service"]
