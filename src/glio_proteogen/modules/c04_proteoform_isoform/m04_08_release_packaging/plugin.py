"""Strict validate-then-run plugin boundary for M04-08 releases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_08 import (
    M0408_MAX_CANONICAL_REQUEST_BYTES,
    BuildProteoformReleaseRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
    BuiltProteoformRelease,
    preflight_proteoform_release_authorization,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.service import (
        M0408Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(BuildProteoformReleaseRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M04-08",
    title="Provenance and release packaging",
    version="1.0.0",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "private keys, signing secrets, or release-authority claims",
        "protein-RNA discordance, proteoform, proteotype, subtype, or kinase inference",
        "generic all-omics fusion or direct treatment recommendation",
        "mutation, relabeling, or disagreement erasure in upstream evidence",
        "missing or unsupported evidence interpreted as negative",
    ),
)


@dataclass(frozen=True, slots=True)
class ProteoformReleaseSubmission:
    request: object
    artifacts_by_path: Mapping[str, object]
    stage_results_by_module: Mapping[str, object]


_TOKEN_SEAL: Final = object()


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0408Request:
    request: BuildProteoformReleaseRequest
    artifacts_by_path: Mapping[str, object]
    stage_results_by_module: Mapping[str, object]
    _seal: object


_ISSUED_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM0408Request,
        tuple[BuildProteoformReleaseRequest, str],
    ]
] = WeakKeyDictionary()


def _token_is_issued(token: ValidatedM0408Request) -> bool:
    snapshot = _ISSUED_TOKENS.get(token)
    return (
        snapshot is not None
        and token._seal is _TOKEN_SEAL
        and snapshot[0] is token.request
        and snapshot[1] == canonical_request_digest(token.request)
    )


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-08 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-08 validation requires a proteoform release submission")


class M0408Plugin(ModulePlugin[object, ValidatedM0408Request, BuiltProteoformRelease]):
    """Expose M04-08 through the common ABI without owning signing keys."""

    __slots__ = ("_service",)

    def __init__(self, service: M0408Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0408Request:
        if not isinstance(request, ProteoformReleaseSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            decoded = strict_json_loads(serialized, max_bytes=M0408_MAX_CANONICAL_REQUEST_BYTES)
            preflight_proteoform_release_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(serialized, strict=True)
        token = ValidatedM0408Request(
            request=self._service.validate_request(candidate),
            artifacts_by_path=request.artifacts_by_path,
            stage_results_by_module=request.stage_results_by_module,
            _seal=_TOKEN_SEAL,
        )
        _ISSUED_TOKENS[token] = (token.request, canonical_request_digest(token.request))
        return token

    def run(self, request: ValidatedM0408Request) -> BuiltProteoformRelease:
        if type(request) is not ValidatedM0408Request or not _token_is_issued(request):
            raise _InvalidExecutionTokenError
        return self._service.build(
            request.request, request.artifacts_by_path, request.stage_results_by_module
        )


__all__ = ["M0408Plugin", "ProteoformReleaseSubmission", "ValidatedM0408Request"]
