"""Strict validate-then-run plugin boundary for M05-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m05_03 import PtmLocalizationRawInputValidationResult
from glio_proteogen.contracts.m05_04 import (
    M0504_MAX_CANONICAL_REQUEST_BYTES,
    ComputePtmLocalizationQualityMetricsRequest,
    PtmLocalizationQualityResult,
    normalized_raw_input_result,
    normalized_request,
)
from glio_proteogen.contracts.m05_04.v1 import (
    _request_capability_is_issued,
    _ValidatedRequestCapability,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics.engine import (
    _validate_json_request_capability,
    _validate_outer_request_shape,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics.service import (
        M0504Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M05-04",
    title="PTM localization quality metric computation",
    version="1.0.0",
    owner="Platform engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "external scientific content, raw rows, spectra, sequences, or measurements",
        "identity, consent, protein, proteoform, isoform, or PTM localization inference",
        "variant peptide, proteogenomic state, proteotype, or subtype emission",
        "kinase-state inference, copy-number regression, all-omics fusion, or treatment advice",
        "upstream mutation, relabeling, deduplication, authority authentication, "
        "model execution, or event persistence",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0504Request:
    """Opaque capability proving strict M05-04 request acceptance."""

    request: ComputePtmLocalizationQualityMetricsRequest
    _capability: _ValidatedRequestCapability
    _seal: object


@dataclass(frozen=True, slots=True)
class _IssuedM0504TokenSnapshot:
    request: ComputePtmLocalizationQualityMetricsRequest
    request_bytes: bytes
    raw_input_result: PtmLocalizationRawInputValidationResult
    raw_input_bytes: bytes
    capability: _ValidatedRequestCapability


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0504Request, _IssuedM0504TokenSnapshot]] = (
    WeakKeyDictionary()
)


def _token_is_issued(token: ValidatedM0504Request) -> bool:
    snapshot = _ISSUED_TOKENS.get(token)
    try:
        request = object.__getattribute__(token, "request")
        capability = object.__getattribute__(token, "_capability")
        if (
            snapshot is None
            or type(request) is not ComputePtmLocalizationQualityMetricsRequest
            or type(capability) is not _ValidatedRequestCapability
            or snapshot.request is not request
            or snapshot.capability is not capability
            or capability.request is not request
            or not _request_capability_is_issued(capability)
        ):
            return False
        _validate_outer_request_shape(request)
        raw_input = object.__getattribute__(request, "raw_input_result")
        return (
            type(raw_input) is PtmLocalizationRawInputValidationResult
            and snapshot.raw_input_result is raw_input
            and snapshot.request_bytes == canonical_json_bytes(normalized_request(request))
            and snapshot.raw_input_bytes
            == canonical_json_bytes(normalized_raw_input_result(raw_input))
        )
    except Exception:  # noqa: BLE001 - mutated or forged capabilities fail closed.
        return False


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-04 execution requires a validated request token")


class M0504Plugin(ModulePlugin[object, ValidatedM0504Request, PtmLocalizationQualityResult]):
    """Grant one immutable aggregate-quality execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0504Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0504Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            decoded = strict_json_loads(
                serialized,
                max_bytes=M0504_MAX_CANONICAL_REQUEST_BYTES,
            )
            capability = _validate_json_request_capability(decoded, serialized)
        else:
            capability = self._service._admit_request(candidate)
        typed = capability.request
        raw_input = typed.raw_input_result
        token = ValidatedM0504Request(
            request=typed,
            _capability=capability,
            _seal=_TOKEN_SEAL,
        )
        _ISSUED_TOKENS[token] = _IssuedM0504TokenSnapshot(
            request=typed,
            request_bytes=canonical_json_bytes(normalized_request(typed)),
            raw_input_result=raw_input,
            raw_input_bytes=canonical_json_bytes(normalized_raw_input_result(raw_input)),
            capability=capability,
        )
        return token

    def run(self, request: ValidatedM0504Request) -> PtmLocalizationQualityResult:
        if (
            type(request) is not ValidatedM0504Request
            or request._seal is not _TOKEN_SEAL
            or not _token_is_issued(request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request._capability)


__all__ = ["M0504Plugin", "ValidatedM0504Request"]
