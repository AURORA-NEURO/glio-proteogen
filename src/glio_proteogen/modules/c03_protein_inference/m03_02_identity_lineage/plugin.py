"""Strict validate-then-run plugin boundary for M03-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_02.v1 import (
    M0302_MAX_CANONICAL_REQUEST_BYTES,
    ProteinInferenceIdentityLineageResolution,
    ReconcileProteinInferenceIdentityLineageRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage.engine import (
    preflight_protein_identity_lineage_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage.service import (
        M0302Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileProteinInferenceIdentityLineageRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M03-02",
    title="Identity and lineage reconciliation",
    version="1.0.0",
    owner="ML engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "raw peptide, accession, copy-number, abundance, activity, or clinical payload",
        "new or merged patient, specimen, aliquot, section, analyte, or run identity",
        "upstream mutation, relabeling, disagreement erasure, or consent inference",
        "protein, complex, kinase, subtype, treatment, or clinical inference",
        "generic all-omics fusion or missing-as-negative interpretation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0302Request:
    """Opaque capability proving that the M03-02 boundary accepted the request."""

    request: ReconcileProteinInferenceIdentityLineageRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-02 execution requires a validated request token")


class M0302Plugin(
    ModulePlugin[
        object,
        ValidatedM0302Request,
        ProteinInferenceIdentityLineageResolution,
    ]
):
    """Expose immutable lineage and CN corroboration receipts without wider authority."""

    __slots__ = ("_service",)

    def __init__(self, service: M0302Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0302Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M0302_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_protein_identity_lineage_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0302Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM0302Request,
    ) -> ProteinInferenceIdentityLineageResolution:
        if not isinstance(request, ValidatedM0302Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0302Plugin", "ValidatedM0302Request"]
