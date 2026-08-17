"""Strict validate-then-run plugin boundary for M04-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m04_05 import (
    ProteoformArtifactDetectionResult,
)
from glio_proteogen.contracts.m04_05 import (
    normalized_result as normalized_m0405_result,
)
from glio_proteogen.contracts.m04_06 import (
    M0406_MAX_CANONICAL_REQUEST_BYTES,
    HarmonizeProteoformAnalysisRequest,
    ProteoformHarmonizationResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization.engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest
    from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization.service import (
        M0406Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M04-06",
    title="Harmonization and normalization engine",
    version="1.0.0",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw spectra, peptide strings, accessions, sequences, or abundance measurements",
        "protein, proteoform, protein-RNA discordance, subtype, proteotype, or kinase inference",
        "calibrated probability, clinical decision, or treatment recommendation",
        "artifact-held evidence traversal, imputation, relabeling, or disagreement erasure",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0406Request:
    """Opaque capability holding one immutable validated harmonization request."""

    request: HarmonizeProteoformAnalysisRequest
    _seal: object


_ISSUED_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM0406Request,
        tuple[
            HarmonizeProteoformAnalysisRequest,
            Sha256Digest,
            ProteoformArtifactDetectionResult,
            Sha256Digest,
        ],
    ]
] = WeakKeyDictionary()


def _upstream_snapshot(
    request: HarmonizeProteoformAnalysisRequest,
) -> Sha256Digest:
    return sha256_digest(normalized_m0405_result(request.artifact_result))


def _token_is_issued(token: ValidatedM0406Request) -> bool:
    snapshot = _ISSUED_TOKENS.get(token)
    if snapshot is None:
        return False
    try:
        return (
            snapshot[0] is token.request
            and snapshot[1] == canonical_request_digest(token.request)
            and snapshot[2] is token.request.artifact_result
            and snapshot[3] == _upstream_snapshot(token.request)
        )
    except Exception:  # noqa: BLE001 - mutated capabilities fail closed.
        return False


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-06 execution requires a validated request token")


class M0406Plugin(ModulePlugin[object, ValidatedM0406Request, ProteoformHarmonizationResult]):
    """Parse strict metadata and grant one typed execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0406Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0406Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = strict_json_loads(
                serialized,
                max_bytes=M0406_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = _validate_json_request(candidate, serialized)
        else:
            typed = self._service.validate_request(candidate)
        token = ValidatedM0406Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (
            typed,
            canonical_request_digest(typed),
            typed.artifact_result,
            _upstream_snapshot(typed),
        )
        return token

    def run(self, request: ValidatedM0406Request) -> ProteoformHarmonizationResult:
        if (
            type(request) is not ValidatedM0406Request
            or request._seal is not _TOKEN_SEAL
            or not _token_is_issued(request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0406Plugin", "ValidatedM0406Request"]
