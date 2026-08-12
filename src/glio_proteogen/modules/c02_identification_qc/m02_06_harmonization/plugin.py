"""Strict validate-then-run plugin for M02-06 identification harmonization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_06 import (
    HarmonizeIdentificationEvidenceRequest,
    IdentificationHarmonizationResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization.engine import (
    preflight_identification_harmonization_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization.service import (
        M0206Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizeIdentificationEvidenceRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M02-06",
    title="Harmonization and normalization engine",
    version="1.0.0",
    owner="Data engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "protein-subtype, proteotype, or biological inference",
        "kinase-state ownership or generic all-omics fusion",
        "upstream result, evidence, identity, or consent mutation",
        "repair, imputation, or negative interpretation of absent evidence",
        "clinical or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0206Request:
    """Opaque capability proving that the M02-06 boundary accepted the request."""

    request: HarmonizeIdentificationEvidenceRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M02-06 execution requires a validated request token")


class M0206Plugin(ModulePlugin[object, ValidatedM0206Request, IdentificationHarmonizationResult]):
    """Expose M02-06 through the common plugin ABI without widening its authority."""

    __slots__ = ("_service",)

    def __init__(self, service: M0206Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0206Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            preflight_identification_harmonization_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0206Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0206Request) -> IdentificationHarmonizationResult:
        if not isinstance(request, ValidatedM0206Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0206Plugin", "ValidatedM0206Request"]
