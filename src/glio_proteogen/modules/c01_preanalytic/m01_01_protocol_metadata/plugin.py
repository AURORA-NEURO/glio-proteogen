"""Agent-friendly plugin boundary for M01-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_01.v1 import (
    EvaluateMetadataRequest,
    M0101Output,
    M0101Request,
    RegisterProtocolRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, assert_strict_json

if TYPE_CHECKING:
    from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
        M0101Service,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[RegisterProtocolRequest | EvaluateMetadataRequest]] = (
    TypeAdapter(M0101Request)
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M01-01",
    title="Protocol and metadata specification",
    version="1.0.0",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "kinase state estimation",
        "generic all-omics fusion",
        "treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0101Request:
    """Opaque execution token proving shape and pre-execution checks have run."""

    request: RegisterProtocolRequest | EvaluateMetadataRequest


class M0101Plugin(ModulePlugin[object, ValidatedM0101Request, M0101Output]):
    """Expose strict parse/validate/run phases for agents and other orchestrators."""

    __slots__ = ("_service",)

    def __init__(self, service: M0101Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        """Return the immutable ownership and safety boundary for this module."""

        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0101Request:
        """Strictly parse the closed request union and run fail-closed prechecks."""

        if isinstance(request, bytes | bytearray | str):
            assert_strict_json(request, max_bytes=MAX_JSON_BYTES)
            parsed = _REQUEST_ADAPTER.validate_json(request, strict=True)
        else:
            parsed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        validated = self._service.validate_request(parsed)
        return ValidatedM0101Request(request=validated)

    def run(self, request: ValidatedM0101Request) -> M0101Output:
        """Execute only a token returned by :meth:`validate`."""

        return self._service.execute(request.request)


__all__ = ["M0101Plugin", "ValidatedM0101Request"]
