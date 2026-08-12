"""Stateless application boundary for M02-06 identification harmonization."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_06 import (
    HarmonizeIdentificationEvidenceRequest,
    IdentificationHarmonizationResult,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization.engine import (
    M0206IdentificationHarmonizationEngine,
    preflight_identification_harmonization_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizeIdentificationEvidenceRequest)


class M0206Service:
    """Authorize, strictly validate, and harmonize one immutable request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0206IdentificationHarmonizationEngine | None = None) -> None:
        self._engine = engine or M0206IdentificationHarmonizationEngine()

    @staticmethod
    def validate_request(request: object) -> HarmonizeIdentificationEvidenceRequest:
        preflight_identification_harmonization_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> IdentificationHarmonizationResult:
        return self._engine.harmonize(request)


__all__ = ["M0206Service"]
