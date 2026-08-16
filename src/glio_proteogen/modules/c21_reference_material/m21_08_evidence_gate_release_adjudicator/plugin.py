"""Strict parse-once plugin adapter for M21-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_08 import (
    M2108_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateComplexActivityEvidenceGateRequest,
    ComplexActivityEvidenceGateResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2108Engine, preflight_m2108_authorization
from .service import M2108Service

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateComplexActivityEvidenceGateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityEvidenceGateResult)
_SEAL: Final = object()


@dataclass(frozen=True, slots=True)
class ValidatedM2108Request:
    """Opaque request token issued by the strict parser."""

    request: AdjudicateComplexActivityEvidenceGateRequest
    _seal: object


class M2108Plugin:
    """Plugin enforcing validation exactly once before adjudication."""

    def __init__(self, service: M2108Service | None = None) -> None:
        self._service = service or M2108Service(M2108Engine())

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M21-08",
            title="Evidence gate and release adjudicator",
            version="0.1.0-provisional",
            owner="ML engineering",
            safety_class="S3",
            gate="G5",
            prohibited_outputs=(
                "complex-activity estimate",
                "identity or consent inference",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2108Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2108_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2108_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2108_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM2108Request(request=typed, _seal=_SEAL)

    def run(self, request: ValidatedM2108Request) -> ComplexActivityEvidenceGateResult:
        if not isinstance(request, ValidatedM2108Request) or request._seal is not _SEAL:
            raise TypeError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityEvidenceGateResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result, replay=replay)


__all__ = ["M2108Plugin", "ValidatedM2108Request"]
