"""Strict validate-then-run plugin boundary for M02-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_04 import (
    ComputeIdentificationQualityRequest,
    IdentificationQualityProfile,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics.engine import (
    preflight_identification_quality_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics.service import (
        M0204Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(ComputeIdentificationQualityRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M02-04",
    title="Quality metric computation",
    version="1.0.0",
    owner="Quality engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "protein-subtype, proteotype, or biological inference",
        "kinase-state ownership or generic all-omics fusion",
        "upstream identity, consent, or evidence mutation",
        "missing evidence interpreted as a negative finding",
        "clinical or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0204Request:
    request: ComputeIdentificationQualityRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M02-04 execution requires a validated request token")


class M0204Plugin(ModulePlugin[object, ValidatedM0204Request, IdentificationQualityProfile]):
    __slots__ = ("_service",)

    def __init__(self, service: M0204Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0204Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            preflight_identification_quality_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0204Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0204Request) -> IdentificationQualityProfile:
        if not isinstance(request, ValidatedM0204Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0204Plugin", "ValidatedM0204Request"]
