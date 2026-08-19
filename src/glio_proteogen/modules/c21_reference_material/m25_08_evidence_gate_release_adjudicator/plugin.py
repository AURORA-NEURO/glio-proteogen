"""Strict parse-once plugin adapter for M25-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m25_08 import (
    M2508_MAX_CANONICAL_REQUEST_BYTES,
    M2508_MAX_CANONICAL_RESULT_BYTES,
    AdjudicateProteotypeEvidenceGateRequest,
    ProteotypeEvidenceGateResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2508Engine, M2508ReplayError, preflight_m2508_authorization
from .service import M2508Service

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateProteotypeEvidenceGateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeEvidenceGateResult)
@dataclass(frozen=True, slots=True)
class ValidatedM2508Request:
    """Opaque request token issued by the strict parser."""

    request: AdjudicateProteotypeEvidenceGateRequest
    _seal: object
    _request_identity: int = 0
    _request_bytes: bytes = b""


class M2508Plugin:
    """Plugin enforcing validation exactly once before adjudication."""

    def __init__(self, service: M2508Service | None = None) -> None:
        self._service = service or M2508Service(M2508Engine())
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M25-08",
            title="Evidence gate and release adjudicator",
            version="0.1.0-provisional",
            owner="Platform engineering",
            safety_class="S3",
            gate="G5",
            prohibited_outputs=(
                "proteotype estimate",
                "identity or consent inference",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2508Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2508_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2508_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2508_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM2508Request(
            request=typed,
            _seal=self._seal,
            _request_identity=id(typed),
            _request_bytes=canonical_json_bytes(typed.model_dump(mode="json")),
        )

    def run(self, request: ValidatedM2508Request) -> ProteotypeEvidenceGateResult:
        if (
            not isinstance(request, ValidatedM2508Request)
            or request._seal is not self._seal
            or type(request.request) is not AdjudicateProteotypeEvidenceGateRequest
            or id(request.request) != request._request_identity
        ):
            raise TypeError
        if canonical_json_bytes(request.request.model_dump(mode="json")) != request._request_bytes:
            raise TypeError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeEvidenceGateResult:
        try:
            if isinstance(result, (bytes, bytearray, str)):
                decoded = strict_json_loads(result, max_bytes=M2508_MAX_CANONICAL_RESULT_BYTES)
                typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
            else:
                typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError) as error:
            raise M2508ReplayError from error
        return self._service.verify(typed, replay=replay)


__all__ = ["M2508Plugin", "ValidatedM2508Request"]
