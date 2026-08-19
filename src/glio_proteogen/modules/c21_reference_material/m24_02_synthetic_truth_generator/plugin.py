"""Strict validate-then-run plugin for provisional M24-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_02 import (
    M2402_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelSyntheticTruthResult,
    GenerateBiomarkerPanelSyntheticTruthRequest,
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


@dataclass(frozen=True, slots=True)
class ValidatedM2402Request:
    request: GenerateBiomarkerPanelSyntheticTruthRequest


class M2402Plugin(ModulePlugin[object, ValidatedM2402Request, BiomarkerPanelSyntheticTruthResult]):
    __slots__ = ("_service",)

    def __init__(self, service: M2402Service) -> None:
        self._service = service

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
        return ValidatedM2402Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2402Request) -> BiomarkerPanelSyntheticTruthResult:
        if not isinstance(request, ValidatedM2402Request):
            raise TypeError("M24-02 execution requires a validated request token")  # noqa: TRY003
        return self._service.evaluate(request.request)

    def replay(
        self, result: BiomarkerPanelSyntheticTruthResult
    ) -> BiomarkerPanelSyntheticTruthResult:
        return self._service.verify_replay(result)


__all__ = ["M2402Plugin", "SyntheticTruthSubmission", "ValidatedM2402Request"]
