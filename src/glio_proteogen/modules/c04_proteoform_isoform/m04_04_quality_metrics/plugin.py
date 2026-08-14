"""Strict validate-then-run plugin boundary for M04-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m04_04 import (
    M0404_MAX_CANONICAL_REQUEST_BYTES,
    ComputeProteoformQualityMetricsRequest,
    ProteoformQualityResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics.engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics.service import (
        M0404Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M04-04",
    title="Proteoform quality metric computation",
    version="1.0.0",
    owner="Data engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "external scientific content, raw rows, spectra, sequences, or measurements",
        "identity, consent, protein, proteoform, isoform, or PTM localization inference",
        "protein-RNA discordance, proteogenomic state, proteotype, or subtype emission",
        "kinase-state inference, copy-number regression, all-omics fusion, or treatment advice",
        "upstream mutation, relabeling, deduplication, authority authentication, "
        "or model execution",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0404Request:
    """Opaque capability proving strict M04-04 request acceptance."""

    request: ComputeProteoformQualityMetricsRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-04 execution requires a validated request token")


class M0404Plugin(ModulePlugin[object, ValidatedM0404Request, ProteoformQualityResult]):
    """Grant one immutable aggregate-quality execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0404Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0404Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            decoded = strict_json_loads(
                serialized,
                max_bytes=M0404_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = _validate_json_request(decoded, serialized)
        else:
            typed = self._service.validate_request(candidate)
        return ValidatedM0404Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM0404Request) -> ProteoformQualityResult:
        if type(request) is not ValidatedM0404Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0404Plugin", "ValidatedM0404Request"]
