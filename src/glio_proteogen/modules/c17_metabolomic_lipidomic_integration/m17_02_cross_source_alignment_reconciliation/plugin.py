"""Strict parse-once plugin adapter for M17-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_02 import (
    M1702_MAX_CANONICAL_REQUEST_BYTES,
    AlignVariantPeptideCrossSourceEvidenceRequest,
    VariantPeptideCrossSourceAlignmentResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1702AlignmentEngine, preflight_alignment_authorization
from .service import M1702Service

_REQUEST_ADAPTER = TypeAdapter(AlignVariantPeptideCrossSourceEvidenceRequest)
_RESULT_ADAPTER = TypeAdapter(VariantPeptideCrossSourceAlignmentResult)
_SEAL: Final = object()


@dataclass(frozen=True, slots=True)
class ValidatedM1702Request:
    """Opaque request token issued by the strict parser."""

    request: AlignVariantPeptideCrossSourceEvidenceRequest
    _seal: object


class M1702Plugin:
    """Plugin enforcing validation exactly once before execution."""

    def __init__(self, service: M1702Service | None = None) -> None:
        self._service = service or M1702Service(M1702AlignmentEngine())

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M17-02",
            title="Cross-source alignment and reconciliation",
            version="0.1.0-provisional",
            owner="Computational biology",
            safety_class="S2",
            gate="G1",
            prohibited_outputs=(
                "kinase activity",
                "generic all-omics fusion",
                "direct treatment recommendation",
                "identity or consent inference",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM1702Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1702_MAX_CANONICAL_REQUEST_BYTES)
            preflight_alignment_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_alignment_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM1702Request(request=typed, _seal=_SEAL)

    def run(self, request: ValidatedM1702Request) -> VariantPeptideCrossSourceAlignmentResult:
        if not isinstance(request, ValidatedM1702Request) or request._seal is not _SEAL:
            raise TypeError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideCrossSourceAlignmentResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result, replay=replay)


__all__ = ["M1702Plugin", "ValidatedM1702Request"]
