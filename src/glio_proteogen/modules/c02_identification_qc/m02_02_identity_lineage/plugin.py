"""Strict validate-then-run plugin boundary for M02-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_02 import (
    IdentityBindingEvaluation,
    ValidateIdentityBindingsRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage.engine import (
    preflight_identity_binding_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage.service import (
        M0202Service,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[ValidateIdentityBindingsRequest]] = TypeAdapter(
    ValidateIdentityBindingsRequest
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M02-02",
    title="Identity and lineage binding reconciliation",
    version="1.0.0",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "identity inference, linking, merging, or relabeling",
        "raw identity or token disclosure",
        "kinase-state or treatment inference",
        "clinical or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0202Request:
    request: ValidateIdentityBindingsRequest


class M0202Plugin(ModulePlugin[object, ValidatedM0202Request, IdentityBindingEvaluation]):
    """Expose strict parse, authorization, validation, and execution phases."""

    __slots__ = ("_service",)

    def __init__(self, service: M0202Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, candidate: object) -> ValidatedM0202Request:
        if isinstance(candidate, bytes | bytearray | str):
            raw = candidate
            decoded = strict_json_loads(raw, max_bytes=MAX_JSON_BYTES)
            preflight_identity_binding_authorization(decoded)
            request = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        else:
            request = self._service.validate_request(candidate)
        return ValidatedM0202Request(request=request)

    def run(self, request: ValidatedM0202Request) -> IdentityBindingEvaluation:
        if not isinstance(request, ValidatedM0202Request):
            raise TypeError
        return self._service.execute(request.request)


__all__ = ["M0202Plugin", "ValidatedM0202Request"]
