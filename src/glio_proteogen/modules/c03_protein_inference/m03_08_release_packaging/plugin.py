"""Strict validate-then-run plugin for M03-08 protein-inference releases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_08 import (
    M0308_MAX_CANONICAL_REQUEST_BYTES,
    BuildProteinInferenceReleaseRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.engine import (
    BuiltProteinInferenceRelease,
    preflight_protein_inference_release_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.service import (
        M0308Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(BuildProteinInferenceReleaseRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M03-08",
    title="Provenance and release packaging",
    version="1.0.0",
    owner="Computational biology",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "private keys, signing secrets, or release-authority claims",
        "protein, proteoform, complex activity, kinase state, or biological inference",
        "generic omics fusion or treatment recommendation",
        "mutation or relabeling of upstream evidence",
        "missing or unsupported evidence interpreted as negative",
    ),
)


@dataclass(frozen=True, slots=True)
class ProteinInferenceReleaseSubmission:
    request: object
    artifacts_by_path: Mapping[str, object]
    stage_results_by_module: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ValidatedM0308Request:
    request: BuildProteinInferenceReleaseRequest
    artifacts_by_path: Mapping[str, object]
    stage_results_by_module: Mapping[str, object]


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-08 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M03-08 validation requires a protein-inference release submission")


class M0308Plugin(ModulePlugin[object, ValidatedM0308Request, BuiltProteinInferenceRelease]):
    """Expose M03-08 through the common ABI without providing a default verifier."""

    __slots__ = ("_service",)

    def __init__(self, service: M0308Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0308Request:
        if not isinstance(request, ProteinInferenceReleaseSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M0308_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_protein_inference_release_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0308Request(
            request=self._service.validate_request(candidate),
            artifacts_by_path=request.artifacts_by_path,
            stage_results_by_module=request.stage_results_by_module,
        )

    def run(self, request: ValidatedM0308Request) -> BuiltProteinInferenceRelease:
        if not isinstance(request, ValidatedM0308Request):
            raise _InvalidExecutionTokenError
        return self._service.build(
            request.request,
            request.artifacts_by_path,
            request.stage_results_by_module,
        )


__all__ = [
    "M0308Plugin",
    "ProteinInferenceReleaseSubmission",
    "ValidatedM0308Request",
]
