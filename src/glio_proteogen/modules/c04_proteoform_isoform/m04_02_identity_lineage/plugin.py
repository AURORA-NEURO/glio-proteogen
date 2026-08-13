"""Strict validate-then-run plugin boundary for M04-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_02 import (
    M0402_MAX_CANONICAL_REQUEST_BYTES,
    ProteoformIdentityLineageResolution,
    ReconcileProteoformIdentityLineageRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage.engine import (
    preflight_proteoform_identity_lineage_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage.service import (
        M0402Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileProteoformIdentityLineageRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M04-02",
    title="Proteoform identity and artifact-lineage reconciliation",
    version="1.0.0",
    owner="Quality engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "identity, consent, protein, or proteoform inference",
        "protein-RNA discordance, proteogenomic-state, proteotype, or subtype emission",
        "copy-number-to-protein regression, kinase inference, or all-omics fusion",
        "treatment or clinical recommendation",
        "mutation, relabeling, merging, or authority selection over upstream evidence",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0402Request:
    """Opaque capability proving that M04-02 accepted the request boundary."""

    request: ReconcileProteoformIdentityLineageRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-02 execution requires a validated request token")


class M0402Plugin(
    ModulePlugin[
        object,
        ValidatedM0402Request,
        ProteoformIdentityLineageResolution,
    ]
):
    """Expose deterministic lineage closure without widening authority."""

    __slots__ = ("_service",)

    def __init__(self, service: M0402Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0402Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            decoded = strict_json_loads(
                serialized,
                max_bytes=M0402_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_proteoform_identity_lineage_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(serialized, strict=True)
        return ValidatedM0402Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM0402Request,
    ) -> ProteoformIdentityLineageResolution:
        if type(request) is not ValidatedM0402Request:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0402Plugin", "ValidatedM0402Request"]
