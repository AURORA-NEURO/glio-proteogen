"""Strict validate-then-run plugin boundary for M04-07 support routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m04_04 import ProteoformQualityResult
from glio_proteogen.contracts.m04_06 import ProteoformHarmonizationResult
from glio_proteogen.contracts.m04_07 import (
    M0407_MAX_CANONICAL_REQUEST_BYTES,
    ProteoformSupportPrerequisites,
    ProteoformSupportRouteResult,
    RouteProteoformSupportRequest,
    canonical_request_digest,
    normalized_request,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router.engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router.service import (
        M0407Service,
    )

_TOKEN_SEAL: Final = object()
_TOKEN_SNAPSHOT_LENGTH: Final = 6
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M04-07",
    title="Unsupported-case and abstention router",
    version="1.0.0",
    owner="Computational biology",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or abundance measurements",
        "protein-RNA discordance, proteogenomic state, proteotype, or protein-level subtype",
        "protein, proteoform, isoform, modification, or kinase inference",
        "copy-number regression, all-omics fusion, calibrated probability, or treatment",
        "cross-envelope union, missing-as-negative logic, or disagreement erasure",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0407Request:
    """Opaque capability holding one immutable validated support-routing request."""

    request: RouteProteoformSupportRequest
    _seal: object


_ISSUED_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM0407Request,
        tuple[RouteProteoformSupportRequest, object, object, object, str, bytes],
    ]
] = WeakKeyDictionary()


def _request_snapshot(request: RouteProteoformSupportRequest) -> bytes:
    return canonical_json_bytes(normalized_request(request))


def _token_is_issued(token: ValidatedM0407Request) -> bool:
    if type(token) is not ValidatedM0407Request:
        return False
    try:
        snapshot = _ISSUED_TOKENS.get(token)
        if (
            snapshot is None
            or type(snapshot) is not tuple
            or len(snapshot) != _TOKEN_SNAPSHOT_LENGTH
        ):
            return False
        request = token.request
        if type(request) is RouteProteoformSupportRequest:
            prerequisites = request.prerequisites
            if type(prerequisites) is ProteoformSupportPrerequisites:
                quality_result = prerequisites.quality_result
                harmonization_result = prerequisites.harmonization_result
                if (
                    type(quality_result) is ProteoformQualityResult
                    and type(harmonization_result) is ProteoformHarmonizationResult
                    and type(snapshot[4]) is str
                    and type(snapshot[5]) is bytes
                ):
                    return (
                        snapshot[0] is request
                        and snapshot[1] is prerequisites
                        and snapshot[2] is quality_result
                        and snapshot[3] is harmonization_result
                        and snapshot[4] == canonical_request_digest(request)
                        and snapshot[5] == _request_snapshot(request)
                    )
    except Exception:  # noqa: BLE001 - a corrupted capability always fails closed.
        return False
    return False


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-07 execution requires a validated request token")


class M0407Plugin(ModulePlugin[object, ValidatedM0407Request, ProteoformSupportRouteResult]):
    """Parse strict metadata and grant one typed execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0407Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0407Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(
                serialized,
                max_bytes=M0407_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = _validate_json_request(candidate, serialized)
        else:
            typed = self._service.validate_request(candidate)
        token = ValidatedM0407Request(request=typed, _seal=_TOKEN_SEAL)
        prerequisites = typed.prerequisites
        if (
            type(prerequisites) is not ProteoformSupportPrerequisites
            or type(prerequisites.quality_result) is not ProteoformQualityResult
            or type(prerequisites.harmonization_result) is not ProteoformHarmonizationResult
        ):
            raise _InvalidExecutionTokenError
        _ISSUED_TOKENS[token] = (
            typed,
            prerequisites,
            prerequisites.quality_result,
            prerequisites.harmonization_result,
            canonical_request_digest(typed),
            _request_snapshot(typed),
        )
        return token

    def run(self, request: ValidatedM0407Request) -> ProteoformSupportRouteResult:
        if (
            type(request) is not ValidatedM0407Request
            or request._seal is not _TOKEN_SEAL
            or not _token_is_issued(request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0407Plugin", "ValidatedM0407Request"]
