"""Stateless application seam for provisional M06-07 calibration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M0607CalibrationEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m06_07 import CalibrateSelectiveProteinAbundanceRequest


class M0607Service:
    """Strictly validate one request; calibration is intentionally deferred."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M0607CalibrationEngine()

    @staticmethod
    def validate_request(request: object) -> CalibrateSelectiveProteinAbundanceRequest:
        return M0607CalibrationEngine.validate_request(request)

    def calibrate(self, request: object) -> None:
        return self._engine.calibrate(request)


__all__ = ["M0607Service"]
