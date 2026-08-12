"""Strict validate-then-run plugin for M02-08 identification releases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_08 import BuildIdentificationQcReleaseRequest
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging.engine import (
    BuiltIdentificationRelease,
    preflight_identification_release_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging.service import (
        M0208Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(BuildIdentificationQcReleaseRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M02-08",
    title="Provenance and release packaging",
    version="1.0.0",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "private keys, signing secrets, or release-authority claims",
        "protein subtype, proteotype, kinase state, or biological inference",
        "generic omics fusion or treatment recommendation",
        "mutation or relabeling of upstream evidence",
        "missing or unsupported evidence interpreted as negative",
    ),
)


@dataclass(frozen=True, slots=True)
class IdentificationReleaseSubmission:
    request: object
    artifacts_by_path: Mapping[str, object]
    stage_results_by_module: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ValidatedM0208Request:
    request: BuildIdentificationQcReleaseRequest
    artifacts_by_path: Mapping[str, object]
    stage_results_by_module: Mapping[str, object]


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M02-08 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M02-08 validation requires an identification release submission")


class M0208Plugin(ModulePlugin[object, ValidatedM0208Request, BuiltIdentificationRelease]):
    """Expose M02-08 through the common ABI without providing a default verifier."""

    __slots__ = ("_service",)

    def __init__(self, service: M0208Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0208Request:
        if not isinstance(request, IdentificationReleaseSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            preflight_identification_release_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0208Request(
            request=self._service.validate_request(candidate),
            artifacts_by_path=request.artifacts_by_path,
            stage_results_by_module=request.stage_results_by_module,
        )

    def run(self, request: ValidatedM0208Request) -> BuiltIdentificationRelease:
        if not isinstance(request, ValidatedM0208Request):
            raise _InvalidExecutionTokenError
        return self._service.build(
            request.request,
            request.artifacts_by_path,
            request.stage_results_by_module,
        )


__all__ = [
    "IdentificationReleaseSubmission",
    "M0208Plugin",
    "ValidatedM0208Request",
]
