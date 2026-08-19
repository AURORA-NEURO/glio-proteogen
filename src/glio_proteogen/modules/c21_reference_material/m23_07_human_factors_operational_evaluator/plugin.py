"""Strict parse-once plugin boundary for provisional M23-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_07 import (
    M2307_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateVariantPeptideHumanFactorsRequest,
    VariantPeptideHumanFactorsResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2307_authorization

if TYPE_CHECKING:
    from .service import M2307Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateVariantPeptideHumanFactorsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M23-07",
    title="Human-factors and operational evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S3",
    gate="G4",
    prohibited_outputs=(
        "variant-peptide or biological estimate",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class HumanFactorsEvaluationSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


class ValidatedM2307Request:
    """Opaque, instance-bound token for one validated request snapshot."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(self, request: EvaluateVariantPeptideHumanFactorsRequest, seal: object) -> None:
        self.request = request
        self._seal = seal


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2307Request,
        tuple[object, EvaluateVariantPeptideHumanFactorsRequest, bytes],
    ]
] = WeakKeyDictionary()


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M23-07 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M23-07 validation requires a human-factors submission")


class M2307Plugin(
    ModulePlugin[
        object,
        ValidatedM2307Request,
        VariantPeptideHumanFactorsResult,
    ]
):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2307Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2307Request:
        if not isinstance(request, HumanFactorsEvaluationSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2307_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2307_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2307Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_json_bytes(validated))
        return token

    def run(self, request: ValidatedM2307Request) -> VariantPeptideHumanFactorsResult:
        if not isinstance(request, ValidatedM2307Request):
            raise _InvalidExecutionTokenError
        snapshot = _TOKENS.get(request)
        if (
            snapshot is None
            or snapshot[0] is not self._seal
            or request._seal is not self._seal
            or snapshot[1] is not request.request
            or snapshot[2] != canonical_json_bytes(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service.evaluate(snapshot[1])

    def replay(
        self,
        result: VariantPeptideHumanFactorsResult,
    ) -> VariantPeptideHumanFactorsResult:
        return self._service.replay(result)


__all__ = ["HumanFactorsEvaluationSubmission", "M2307Plugin", "ValidatedM2307Request"]
