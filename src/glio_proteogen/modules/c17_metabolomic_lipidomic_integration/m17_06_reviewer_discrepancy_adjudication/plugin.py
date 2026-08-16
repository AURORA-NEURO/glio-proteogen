"""Strict parse-once plugin adapter for M17-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_06 import (
    M1706_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateVariantPeptideDiscrepancyQueueRequest,
    VariantPeptideAdjudicationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1706AdjudicationEngine, preflight_adjudication_authorization
from .service import M1706Service

_REQUEST_ADAPTER = TypeAdapter(AdjudicateVariantPeptideDiscrepancyQueueRequest)
_RESULT_ADAPTER = TypeAdapter(VariantPeptideAdjudicationResult)
_SEAL: Final = object()


@dataclass(frozen=True, slots=True)
class ValidatedM1706Request:
    """Opaque request token issued by the strict parser."""

    request: AdjudicateVariantPeptideDiscrepancyQueueRequest
    _seal: object


class M1706Plugin:
    """Plugin enforcing validation exactly once before execution."""

    def __init__(self, service: M1706Service | None = None) -> None:
        self._service = service or M1706Service(M1706AdjudicationEngine())

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M17-06",
            title="Reviewer discrepancy and adjudication queue",
            version="0.1.0-provisional",
            owner="Clinical science",
            safety_class="S2",
            gate="G4",
            prohibited_outputs=(
                "kinase activity",
                "generic all-omics fusion",
                "direct treatment recommendation",
                "identity or consent inference",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM1706Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1706_MAX_CANONICAL_REQUEST_BYTES)
            preflight_adjudication_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_adjudication_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM1706Request(request=typed, _seal=_SEAL)

    def run(self, request: ValidatedM1706Request) -> VariantPeptideAdjudicationResult:
        if not isinstance(request, ValidatedM1706Request) or request._seal is not _SEAL:
            raise TypeError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideAdjudicationResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result, replay=replay)


__all__ = ["M1706Plugin", "ValidatedM1706Request"]
