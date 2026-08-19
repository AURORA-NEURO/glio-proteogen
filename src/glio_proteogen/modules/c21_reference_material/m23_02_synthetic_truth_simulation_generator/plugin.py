"""Strict parse-once plugin adapter for M23-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_02 import (
    M2302_MAX_CANONICAL_REQUEST_BYTES,
    GenerateVariantPeptideSyntheticTruthRequest,
    VariantPeptideSyntheticTruthResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2302Engine, preflight_m2302_authorization
from .service import M2302Service

_REQUEST_ADAPTER: Final = TypeAdapter(GenerateVariantPeptideSyntheticTruthRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideSyntheticTruthResult)
@dataclass(frozen=True, slots=True)
class ValidatedM2302Request:
    """Opaque request token issued by the strict parser."""

    request: GenerateVariantPeptideSyntheticTruthRequest
    _seal: object
    _request_identity: int = 0
    _request_bytes: bytes = b""


class M2302Plugin:
    """Plugin enforcing validation exactly once before generation."""

    def __init__(self, service: M2302Service | None = None) -> None:
        self._service = service or M2302Service(M2302Engine())
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M23-02",
            title="Variant peptide synthetic truth and simulation generator",
            version="0.1.0-provisional",
            owner="Platform engineering",
            safety_class="S3",
            gate="G1",
            prohibited_outputs=(
                "variant peptide biological conclusion",
                "identity or consent inference",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2302Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2302_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2302_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2302_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM2302Request(
            request=typed,
            _seal=self._seal,
            _request_identity=id(typed),
            _request_bytes=canonical_json_bytes(typed.model_dump(mode="json")),
        )

    def run(self, request: ValidatedM2302Request) -> VariantPeptideSyntheticTruthResult:
        if (
            not isinstance(request, ValidatedM2302Request)
            or request._seal is not self._seal
            or type(request.request) is not GenerateVariantPeptideSyntheticTruthRequest
            or id(request.request) != request._request_identity
        ):
            raise TypeError
        if canonical_json_bytes(request.request.model_dump(mode="json")) != request._request_bytes:
            raise TypeError
        return self._service.execute(request.request)

    def verify(
        self,
        result: object,
    ) -> VariantPeptideSyntheticTruthResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result)


__all__ = ["M2302Plugin", "ValidatedM2302Request"]
