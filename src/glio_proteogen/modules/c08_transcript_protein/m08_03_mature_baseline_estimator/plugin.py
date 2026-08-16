"""Sealed M08-03 parse-once plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m08_03 import (
    M0803_MAX_CANONICAL_REQUEST_BYTES,
    EstimateProteinSubtypeBaselineRequest,
    ProteinSubtypeBaselineResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator.engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator import (
        service as baseline_service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M08-03",
    title="mature protein-subtype baseline estimator (provisional)",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        (
            "kinase state, generic all-omics fusion, treatment recommendations, "
            "or raw-source traversal"
        ),
        "identity or consent inference and missing-to-negative conversion",
        "parent subtype emission or mutation of caller-owned evidence",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0803Request:
    request: EstimateProteinSubtypeBaselineRequest
    _seal: object


_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0803Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M08-03 execution requires a validated request token")


class M0803Plugin(ModulePlugin[object, ValidatedM0803Request, ProteinSubtypeBaselineResult]):
    """Expose M08-03 through a sealed validate-then-run ABI."""

    __slots__ = ("_service",)

    def __init__(self, service: baseline_service.M0803Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0803Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(serialized, max_bytes=M0803_MAX_CANONICAL_REQUEST_BYTES)
            typed = _validate_json_request(decoded, serialized)
        else:
            typed = self._service.validate_request(request)
        token = ValidatedM0803Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0803Request) -> ProteinSubtypeBaselineResult:
        try:
            snapshot = _ISSUED_TOKENS.get(request)
        except TypeError as error:
            raise _InvalidExecutionTokenError from error
        if (
            type(request) is not ValidatedM0803Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0803Plugin", "ValidatedM0803Request"]
