"""Strict parse-once M20-05 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_05 import (
    M2005_MAX_CANONICAL_REQUEST_BYTES,
    PresentProteinSubtypeHumanReviewWorkspaceRequest,
    ProteinSubtypeHumanReviewWorkspaceResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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


class ValidatedM2005Request:
    """Opaque, instance-bound token for one validated request snapshot."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(
        self, request: PresentProteinSubtypeHumanReviewWorkspaceRequest, seal: object
    ) -> None:
        self.request = request
        self._seal = seal


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2005Request,
        tuple[object, PresentProteinSubtypeHumanReviewWorkspaceRequest, bytes],
    ]
] = WeakKeyDictionary()


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

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2005Service) -> None:
        self._service = service
        self._seal = object()

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
        validated = self._service.validate_request(candidate)
        token = ValidatedM2005Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_json_bytes(validated))
        return token

    def run(self, request: ValidatedM2005Request) -> ProteinSubtypeHumanReviewWorkspaceResult:
        if not isinstance(request, ValidatedM2005Request):
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
        return self._service.present(snapshot[1])

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
