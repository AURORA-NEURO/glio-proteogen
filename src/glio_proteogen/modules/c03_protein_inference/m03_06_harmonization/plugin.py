"""Strict validate-then-run plugin boundary for M03-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_06 import (
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceHarmonizationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization.engine import (
    _plain_value,
    preflight_protein_inference_harmonization_authorization,
    prepare_harmonization_request_candidate,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization.service import (
        M0306Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizeProteinInferenceSupportRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M03-06",
    title="Harmonization and normalization engine",
    version="1.0.0",
    owner="Platform engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or abundance measurements",
        "protein, proteoform, complex-activity, subtype, proteotype, or kinase inference",
        "calibrated probability, clinical decision, or treatment recommendation",
        "artifact-held evidence traversal, imputation, relabeling, or disagreement erasure",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0306Request:
    """Opaque capability holding one immutable validated harmonization request."""

    request: HarmonizeProteinInferenceSupportRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-06 execution requires a validated request token")


class M0306Plugin(ModulePlugin[object, ValidatedM0306Request, ProteinInferenceHarmonizationResult]):
    """Parse strict metadata and grant one typed execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0306Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0306Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M0306_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_protein_inference_harmonization_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(
                    prepare_harmonization_request_candidate(_plain_value(decoded))
                ),
                strict=True,
            )
        return ValidatedM0306Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0306Request) -> ProteinInferenceHarmonizationResult:
        if not isinstance(request, ValidatedM0306Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0306Plugin", "ValidatedM0306Request"]
