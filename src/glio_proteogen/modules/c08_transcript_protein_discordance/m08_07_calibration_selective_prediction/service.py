"""Stateless application boundary for provisional M08-07."""

from glio_proteogen.contracts.m08_07 import (
    CalibrateProteinSubtypeSelectivePredictionRequest,
    ProteinSubtypeSelectivePredictionResult,
)

from .engine import M0807CalibrationEngine, preflight_m0807_authorization


class M0807Service:
    """Authorize, strictly validate, and execute one M08-07 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0807CalibrationEngine | None = None) -> None:
        self._engine = engine or M0807CalibrationEngine()

    @staticmethod
    def validate_request(request: object) -> CalibrateProteinSubtypeSelectivePredictionRequest:
        preflight_m0807_authorization(request)
        return CalibrateProteinSubtypeSelectivePredictionRequest.model_validate(
            request,
            strict=True,
        )

    def _execute_validated(
        self,
        request: CalibrateProteinSubtypeSelectivePredictionRequest,
    ) -> ProteinSubtypeSelectivePredictionResult:
        return self._engine.calibrate(request)

    def execute(self, request: object) -> ProteinSubtypeSelectivePredictionResult:
        return self._engine.calibrate(request)


__all__ = ["M0807Service"]
