"""Strict validate-then-run plugin boundary for M03-07 support routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_07 import (
    M0307_MAX_CANONICAL_REQUEST_BYTES,
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router.engine import (
    preflight_protein_inference_support_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c03_protein_inference.m03_07_support_router.service import (
        M0307Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(RouteProteinInferenceSupportRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M03-07",
    title="Unsupported-case and abstention router",
    version="1.0.0",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or abundance measurements",
        "protein, proteoform, complex-activity, subtype, proteotype, or kinase inference",
        "calibrated probability, clinical decision, or treatment recommendation",
        "cross-envelope union, missing-as-negative logic, or disagreement erasure",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0307Request:
    """Opaque capability holding one immutable validated support-routing request."""

    request: RouteProteinInferenceSupportRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-07 execution requires a validated request token")


class M0307Plugin(ModulePlugin[object, ValidatedM0307Request, ProteinInferenceSupportRouteResult]):
    """Parse strict metadata and grant one typed execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0307Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0307Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M0307_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_protein_inference_support_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(decoded),
                strict=True,
            )
        return ValidatedM0307Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0307Request) -> ProteinInferenceSupportRouteResult:
        if not isinstance(request, ValidatedM0307Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0307Plugin", "ValidatedM0307Request"]
