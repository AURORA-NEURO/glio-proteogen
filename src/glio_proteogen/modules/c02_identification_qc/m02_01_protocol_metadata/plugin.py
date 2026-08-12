"""Strict validate-then-run plugin boundary for M02-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_01 import (
    ConformanceEvaluation,
    EvaluateConformanceRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata.engine import (
    preflight_conformance_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata.service import (
        M0201Service,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[EvaluateConformanceRequest]] = TypeAdapter(
    EvaluateConformanceRequest
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M02-01",
    title="Protocol and metadata specification",
    version="1.0.0",
    owner="Computational biology",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "unit conversion or metadata imputation",
        "negative scientific finding from unresolved metadata",
        "proteotype or kinase-state inference",
        "clinical or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0201Request:
    request: EvaluateConformanceRequest


class M0201Plugin(ModulePlugin[object, ValidatedM0201Request, ConformanceEvaluation]):
    """Expose strict parse, authorization, validation, and execution phases."""

    __slots__ = ("_service",)

    def __init__(self, service: M0201Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, candidate: object) -> ValidatedM0201Request:
        if isinstance(candidate, bytes | bytearray | str):
            raw = candidate
            decoded = strict_json_loads(raw, max_bytes=MAX_JSON_BYTES)
            preflight_conformance_authorization(decoded)
            request = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        else:
            request = self._service.validate_request(candidate)
        return ValidatedM0201Request(request=request)

    def run(self, request: ValidatedM0201Request) -> ConformanceEvaluation:
        if not isinstance(request, ValidatedM0201Request):
            raise TypeError
        return self._service.execute(request.request)


__all__ = ["M0201Plugin", "ValidatedM0201Request"]
