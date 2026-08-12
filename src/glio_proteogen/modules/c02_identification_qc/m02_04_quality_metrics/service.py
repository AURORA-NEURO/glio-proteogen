"""Thin stateless service for M02-04 identification quality."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_04 import (
    ComputeIdentificationQualityRequest,
    IdentificationQualityProfile,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics.engine import (
    M0204IdentificationQualityEngine,
    preflight_identification_quality_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ComputeIdentificationQualityRequest)


class M0204Service:
    def __init__(self, engine: M0204IdentificationQualityEngine | None = None) -> None:
        self._engine = engine or M0204IdentificationQualityEngine()

    @staticmethod
    def validate_request(request: object) -> ComputeIdentificationQualityRequest:
        preflight_identification_quality_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> IdentificationQualityProfile:
        return self._engine.compute(request)


__all__ = ["M0204Service"]
