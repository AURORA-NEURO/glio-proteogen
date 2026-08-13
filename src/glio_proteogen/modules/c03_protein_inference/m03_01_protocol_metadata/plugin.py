"""Strict validate-then-run plugin boundary for M03-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_01.v1 import (
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata.engine import (
    preflight_protein_inference_protocol_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata.service import (
        M0301Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinInferenceProtocolRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M03-01",
    title="Protocol and metadata specification",
    version="1.0.0",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "observed peptide or accession assignment",
        "protein, proteoform, subtype, or proteotype inference",
        "complex-activity or kinase-activity inference",
        "generic all-omics fusion",
        "treatment or clinical recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0301Request:
    """Opaque capability proving that the M03-01 boundary accepted the request."""

    request: EvaluateProteinInferenceProtocolRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-01 execution requires a validated request token")


class M0301Plugin(
    ModulePlugin[
        object,
        ValidatedM0301Request,
        ProteinInferenceProtocolConformanceResult,
    ]
):
    """Expose protocol conformance without widening scientific authority."""

    __slots__ = ("_service",)

    def __init__(self, service: M0301Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0301Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            preflight_protein_inference_protocol_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0301Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM0301Request,
    ) -> ProteinInferenceProtocolConformanceResult:
        if not isinstance(request, ValidatedM0301Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0301Plugin", "ValidatedM0301Request"]
