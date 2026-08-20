"""Strict parse-once plugin boundary for M27-02."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_02 import (
    M2702_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityLineageResult,
    ResolveComplexActivityLineageRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service.engine import (
    preflight_m2702_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service.service import (
        M2702Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(ResolveComplexActivityLineageRequest)
_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M27-02",
    title="Complex-activity lineage service",
    version="0.1.0-provisional",
    owner="ML engineering",
    safety_class="S3",
    gate="G0",
    prohibited_outputs=(
        "complex-activity, protein, proteoform, isoform, or glioma biology inference",
        "kinase activity, all-omics fusion, treatment, identity, or consent inference",
        "upstream mutation, relabeling, disagreement erasure, or source selection",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM2702Request:
    """Opaque capability proving strict M27-02 request validation."""

    request: ResolveComplexActivityLineageRequest
    _seal: object | None = field(default=None, repr=False, compare=False)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M27-02 execution requires a validated request token")


class M2702Plugin(ModulePlugin[object, ValidatedM2702Request, ComplexActivityLineageResult]):
    """Expose M27-02 through strict JSON and typed request parity."""

    __slots__ = ("_service",)

    def __init__(self, service: M2702Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2702Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            decoded = strict_json_loads(
                serialized,
                max_bytes=M2702_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_m2702_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(serialized, strict=True)
        return ValidatedM2702Request(
            request=self._service.validate_request(candidate),
            _seal=_TOKEN_SEAL,
        )

    def run(self, request: ValidatedM2702Request) -> ComplexActivityLineageResult:
        if type(request) is not ValidatedM2702Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M2702Plugin", "ValidatedM2702Request"]
