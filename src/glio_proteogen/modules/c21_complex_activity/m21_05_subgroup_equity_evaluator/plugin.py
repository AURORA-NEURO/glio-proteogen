"""Strict parse-once plugin adapter for M21-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_05 import (
    M2105_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivitySubgroupEvaluationResult,
    EvaluateComplexActivitySubgroupEquityRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2105Engine, preflight_m2105_authorization
from .service import M2105Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateComplexActivitySubgroupEquityRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivitySubgroupEvaluationResult)
_SEAL: Final = object()


@dataclass(frozen=True, slots=True)
class ValidatedM2105Request:
    """Opaque request token issued by the strict parser."""

    request: EvaluateComplexActivitySubgroupEquityRequest
    _seal: object


class M2105Plugin:
    """Plugin enforcing validation exactly once before execution."""

    def __init__(self, service: M2105Service | None = None) -> None:
        self._service = service or M2105Service(M2105Engine())

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M21-05",
            title="Subgroup equity evaluator",
            version="0.1.0-provisional",
            owner="Scientific engineering",
            safety_class="S3",
            gate="G3",
            prohibited_outputs=(
                "identity or consent inference",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2105Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2105_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2105_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2105_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM2105Request(request=typed, _seal=_SEAL)

    def run(self, request: ValidatedM2105Request) -> ComplexActivitySubgroupEvaluationResult:
        if not isinstance(request, ValidatedM2105Request) or request._seal is not _SEAL:
            raise TypeError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivitySubgroupEvaluationResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result, replay=replay)


__all__ = ["M2105Plugin", "ValidatedM2105Request"]
