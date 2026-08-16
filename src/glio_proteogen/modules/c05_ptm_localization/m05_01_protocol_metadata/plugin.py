"""Strict validate-then-run plugin boundary for M05-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m05_01 import (
    M0501_MAX_CANONICAL_REQUEST_BYTES,
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationProtocolConformanceResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata.engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata.service import (
        M0501Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M05-01",
    title="PTM-localization protocol and metadata specification",
    version="1.0.0",
    owner="Quality engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "raw measurements, spectra, sequences, accessions, biological payloads, or external "
        "content",
        "PTM localization, variant peptide, proteogenomic state, proteotype, or subtype inference",
        "kinase-state ownership, all-omics fusion, treatment advice, or clinical decisions",
        "upstream mutation, relabeling, disagreement erasure, or missing-as-negative conversion",
        "identity or consent inference, model fitting, prediction, scoring, or calibration",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0501Request:
    request: EvaluatePtmLocalizationProtocolRequest
    _seal: object


_ISSUED_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM0501Request,
        tuple[EvaluatePtmLocalizationProtocolRequest, bytes],
    ]
] = WeakKeyDictionary()


def _token_is_issued(token: ValidatedM0501Request) -> bool:
    snapshot = _ISSUED_TOKENS.get(token)
    try:
        return (
            snapshot is not None
            and snapshot[0] is token.request
            and snapshot[1] == canonical_json_bytes(token.request)
        )
    except Exception:  # noqa: BLE001 - a mutated token fails closed.
        return False


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-01 execution requires a validated request token")


class M0501Plugin(
    ModulePlugin[
        object,
        ValidatedM0501Request,
        PtmLocalizationProtocolConformanceResult,
    ]
):
    """Grant one immutable M05-01 execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0501Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0501Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(
                serialized,
                max_bytes=M0501_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = _validate_json_request(candidate, serialized)
        else:
            typed = self._service.validate_request(candidate)
        token = ValidatedM0501Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_json_bytes(typed))
        return token

    def run(
        self,
        request: ValidatedM0501Request,
    ) -> PtmLocalizationProtocolConformanceResult:
        if (
            type(request) is not ValidatedM0501Request
            or request._seal is not _TOKEN_SEAL
            or not _token_is_issued(request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0501Plugin", "ValidatedM0501Request"]
