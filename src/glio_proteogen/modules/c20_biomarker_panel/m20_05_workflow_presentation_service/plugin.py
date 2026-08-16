"""Strict parse-once M20-05 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_05 import (
    M2005_MAX_CANONICAL_REQUEST_BYTES,
    PresentProteinSubtypeHumanReviewWorkspaceRequest,
    ProteinSubtypeHumanReviewWorkspaceResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2005_authorization

if TYPE_CHECKING:
    from .service import M2005Service

_REQUEST_ADAPTER: Final = TypeAdapter(PresentProteinSubtypeHumanReviewWorkspaceRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M20-05",
    title="Workflow presentation service (provisional)",
    version="0.1.0-provisional",
    owner="Platform engineering",
    safety_class="S2",
    gate="G4",
    prohibited_outputs=(
        "protein-subtype inference or identity inference",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "upstream evidence mutation or disagreement erasure",
        "unsupported or missing evidence converted to a negative finding",
    ),
)


@dataclass(frozen=True, slots=True)
class WorkflowPresentationSubmission:
    """Opaque submission wrapper that delays parsing until validation."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2005Request:
    """Opaque capability proving strict M20-05 request validation."""

    request: PresentProteinSubtypeHumanReviewWorkspaceRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M20-05 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M20-05 validation requires a workflow presentation submission")


class M2005Plugin(
    ModulePlugin[object, ValidatedM2005Request, ProteinSubtypeHumanReviewWorkspaceResult]
):
    """Expose M20-05 through validate-then-run without an authority bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2005Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2005Request:
        if not isinstance(request, WorkflowPresentationSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M2005_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_m2005_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2005Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM2005Request) -> ProteinSubtypeHumanReviewWorkspaceResult:
        if not isinstance(request, ValidatedM2005Request):
            raise _InvalidExecutionTokenError
        return self._service.present(request.request)

    def replay(
        self,
        result: ProteinSubtypeHumanReviewWorkspaceResult,
    ) -> ProteinSubtypeHumanReviewWorkspaceResult:
        return self._service.replay(result)


__all__ = [
    "M2005Plugin",
    "ValidatedM2005Request",
    "WorkflowPresentationSubmission",
]
