"""Strict parse-once plugin boundary for provisional M22-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_05 import (
    M2205_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteinRnaDiscordanceSubgroupEquityRequest,
    ProteinRnaDiscordanceSubgroupEvaluationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2205_authorization

if TYPE_CHECKING:
    from .service import M2205Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinRnaDiscordanceSubgroupEquityRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M22-05",
    title="Subgroup equity evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "protein-RNA discordance or biological estimate",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class EquityEvaluationSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2205Request:
    """Opaque capability proving strict M22-05 request validation."""

    request: EvaluateProteinRnaDiscordanceSubgroupEquityRequest
    _seal: object
    _request_identity: int = 0
    _request_bytes: bytes = b""


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-05 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M22-05 validation requires an equity submission")


class M2205Plugin(
    ModulePlugin[
        object,
        ValidatedM2205Request,
        ProteinRnaDiscordanceSubgroupEvaluationResult,
    ]
):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2205Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2205Request:
        if not isinstance(request, EquityEvaluationSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2205_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2205_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        validated = self._service.validate_request(candidate)
        return ValidatedM2205Request(
            request=validated,
            _seal=self._seal,
            _request_identity=id(validated),
            _request_bytes=canonical_json_bytes(validated),
        )

    def run(self, request: ValidatedM2205Request) -> ProteinRnaDiscordanceSubgroupEvaluationResult:
        if type(request) is not ValidatedM2205Request:
            raise _InvalidExecutionTokenError
        if request._seal is not self._seal or id(request.request) != request._request_identity:
            raise _InvalidExecutionTokenError
        try:
            current_bytes = canonical_json_bytes(request.request)
        except (TypeError, ValueError):
            raise _InvalidExecutionTokenError from None
        if current_bytes != request._request_bytes:
            raise _InvalidExecutionTokenError
        return self._service.evaluate(request.request)

    def replay(
        self,
        result: ProteinRnaDiscordanceSubgroupEvaluationResult,
    ) -> ProteinRnaDiscordanceSubgroupEvaluationResult:
        return self._service.replay(result)


__all__ = ["EquityEvaluationSubmission", "M2205Plugin", "ValidatedM2205Request"]
