"""Stateless application seam for provisional M06-07 calibration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import BuiltCalibration, M0607CalibrationEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m06_07 import (
        CalibrateSelectiveProteinAbundanceRequest,
        CalibrateSelectiveProteinAbundanceVerification,
    )


class M0607Service:
    """Validate, calibrate, replay, and execute one request."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M0607CalibrationEngine()

    @staticmethod
    def validate_request(request: object) -> CalibrateSelectiveProteinAbundanceRequest:
        return M0607CalibrationEngine.validate_request(request)

    def calibrate(self, request: object) -> BuiltCalibration:
        return self._engine.calibrate(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> CalibrateSelectiveProteinAbundanceVerification:
        return self._engine.verify(result, canonical_bytes)

    def execute(self, request: object) -> BuiltCalibration:
        return self._engine.execute(request)


__all__ = ["M0607Service"]
