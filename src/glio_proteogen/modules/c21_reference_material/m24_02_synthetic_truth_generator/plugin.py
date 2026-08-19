"""Strict validate-then-run plugin for provisional M24-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_02 import (
    M2402_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelSyntheticTruthResult,
    GenerateBiomarkerPanelSyntheticTruthRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2402_authorization

if TYPE_CHECKING:
    from .service import M2402Service

_ADAPTER: Final = TypeAdapter(GenerateBiomarkerPanelSyntheticTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-02",
    title="Synthetic truth generator (provisional)",
    version="0.1.0-provisional",
    owner="Scientific engineering",
    safety_class="S3",
    gate="G1",
    prohibited_outputs=(
        "production biomarker or biological truth claims",
        "protein, proteoform, isoform or glioma inference",
        "identity, consent, treatment or kinase inference",
        "unsupported-to-negative conversion",
    ),
)


@dataclass(frozen=True, slots=True)
class SyntheticTruthSubmission:
    request: object


class ValidatedM2402Request:
    """Opaque, instance-bound token for one validated request snapshot."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(self, request: GenerateBiomarkerPanelSyntheticTruthRequest, seal: object) -> None:
        self.request = request
        self._seal = seal


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2402Request,
        tuple[object, GenerateBiomarkerPanelSyntheticTruthRequest, str],
    ]
] = WeakKeyDictionary()


class M2402Plugin(ModulePlugin[object, ValidatedM2402Request, BiomarkerPanelSyntheticTruthResult]):
    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2402Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2402Request:
        if not isinstance(request, SyntheticTruthSubmission):
            raise TypeError(  # noqa: TRY003
                "M24-02 validation requires a synthetic-truth submission"
            )
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2402_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2402_authorization(decoded)
            candidate = _ADAPTER.validate_json(candidate, strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2402Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_request_digest(validated))
        return token

    def run(self, request: ValidatedM2402Request) -> BiomarkerPanelSyntheticTruthResult:
        if not isinstance(request, ValidatedM2402Request):
            raise TypeError("M24-02 execution requires a validated request token")  # noqa: TRY003
        snapshot = _TOKENS.get(request)
        if (
            snapshot is None
            or snapshot[0] is not self._seal
            or request._seal is not self._seal
            or snapshot[1] is not request.request
            or snapshot[2] != canonical_request_digest(request.request)
        ):
            raise TypeError("M24-02 execution requires a validated request token")  # noqa: TRY003
        return self._service.evaluate(snapshot[1])

    def replay(
        self, result: BiomarkerPanelSyntheticTruthResult
    ) -> BiomarkerPanelSyntheticTruthResult:
        return self._service.verify_replay(result)


__all__ = ["M2402Plugin", "SyntheticTruthSubmission", "ValidatedM2402Request"]
