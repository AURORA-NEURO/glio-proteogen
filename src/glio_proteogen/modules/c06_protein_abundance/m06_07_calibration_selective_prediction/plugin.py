"""Strict validate-then-run plugin for provisional M06-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_07 import (
    M0607_CONTRACT_VERSION,
    M0607_MAX_CANONICAL_REQUEST_BYTES,
    M0607_MODULE_ID,
    CalibrateSelectiveProteinAbundanceRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M0607Service

if TYPE_CHECKING:
    from .engine import BuiltCalibration

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateSelectiveProteinAbundanceRequest)
_PROVISIONAL_DESCRIPTOR: Final = {
    "moduleId": M0607_MODULE_ID,
    "title": "Calibration and selective prediction",
    "version": M0607_CONTRACT_VERSION,
    "status": "provisional",
    "operation": "calibrate_selective_protein_abundance",
    "prohibitedOutputs": (
        "kinase_activity",
        "all_omics_fusion",
        "treatment_recommendation",
        "identity_inference",
        "parent_biomarker_panel",
    ),
}


@dataclass(frozen=True, slots=True)
class CalibrationSubmission:
    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM0607Request:
    request: CalibrateSelectiveProteinAbundanceRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-07 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M06-07 validation requires a calibration submission")


class M0607Plugin:
    """Expose M06-07 through a strict, parse-once submission boundary."""

    descriptor = _PROVISIONAL_DESCRIPTOR

    def __init__(self, service: M0607Service | None = None) -> None:
        self._service = service or M0607Service()

    def validate_request(self, request: object) -> CalibrateSelectiveProteinAbundanceRequest:
        return self._service.validate_request(request)

    def validate(self, submission: object) -> ValidatedM0607Request:
        if not isinstance(submission, CalibrationSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            strict_json_loads(candidate, max_bytes=M0607_MAX_CANONICAL_REQUEST_BYTES)
            raw = bytes(candidate) if isinstance(candidate, bytearray) else candidate
            candidate = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        return ValidatedM0607Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0607Request) -> BuiltCalibration:
        if not isinstance(request, ValidatedM0607Request):
            raise _InvalidExecutionTokenError
        return self._service.calibrate(request.request)

    def calibrate(self, request: object) -> BuiltCalibration:
        return self._service.calibrate(request)

    def execute(self, request: object) -> BuiltCalibration:
        return self.calibrate(request)


__all__ = ["CalibrationSubmission", "M0607Plugin", "ValidatedM0607Request"]
