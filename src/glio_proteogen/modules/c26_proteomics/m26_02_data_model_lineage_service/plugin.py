"""Strict parse-once plugin boundary for M26-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_02 import (
    M2602_MAX_CANONICAL_REQUEST_BYTES,
    BuildProteinSubtypeLineageRequest,
    ProteinSubtypeLineageResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.engine import (
    preflight_lineage_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.service import (
        M2602LineageService,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[BuildProteinSubtypeLineageRequest]] = TypeAdapter(
    BuildProteinSubtypeLineageRequest
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M26-02",
    title="Data, model, and version lineage service",
    version="0.1.0-provisional",
    owner="Bioinformatics",
    safety_class="S3",
    gate="G0",
    prohibited_outputs=(
        "protein subtype or proteotype inference",
        "KINOPHOS kinase-state inference",
        "generic all-omics fusion",
        "direct treatment recommendation",
        "identity or consent inference",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM2602Request:
    """Opaque validated token required by :meth:`M2602LineagePlugin.run`."""

    request: BuildProteinSubtypeLineageRequest
    _seal: object | None = None
    _request_identity: int = 0
    _request_bytes: bytes = b""


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M26-02 execution requires a validated request token")


class M2602LineagePlugin(ModulePlugin[object, ValidatedM2602Request, ProteinSubtypeLineageResult]):
    """Parse raw JSON once, validate controls, then expose only a typed token."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2602LineageService) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2602Request:
        if isinstance(request, bytes | bytearray | str):
            raw = request
            decoded = strict_json_loads(raw, max_bytes=M2602_MAX_CANONICAL_REQUEST_BYTES)
            preflight_lineage_authorization(decoded)
            validated = _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        else:
            preflight_lineage_authorization(request)
            validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        typed = self._service.validate_request(validated)
        return ValidatedM2602Request(
            request=typed,
            _seal=self._seal,
            _request_identity=id(typed),
            _request_bytes=canonical_json_bytes(typed.model_dump(mode="json")),
        )

    def run(self, request: ValidatedM2602Request) -> ProteinSubtypeLineageResult:
        if (
            not isinstance(request, ValidatedM2602Request)
            or request._seal is not self._seal
            or type(request.request) is not BuildProteinSubtypeLineageRequest
            or id(request.request) != request._request_identity
        ):
            raise _InvalidExecutionTokenError
        try:
            current_bytes = canonical_json_bytes(request.request.model_dump(mode="json"))
        except Exception as error:
            raise _InvalidExecutionTokenError from error
        if current_bytes != request._request_bytes:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M2602LineagePlugin", "ValidatedM2602Request"]
