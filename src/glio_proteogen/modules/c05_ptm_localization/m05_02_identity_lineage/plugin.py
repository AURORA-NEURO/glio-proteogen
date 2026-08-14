"""Strict validate-then-run plugin boundary for M05-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m05_02 import (
    M0502_MAX_CANONICAL_REQUEST_BYTES,
    PtmLocalizationIdentityLineageResolution,
    ReconcilePtmLocalizationIdentityLineageRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads as _strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage.engine import (
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage.service import (
        M0502Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M05-02",
    title="PTM-localization identity and lineage reconciliation",
    version="1.0.0",
    owner="Clinical science",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "identity, consent, protein, proteoform, or PTM-localization inference",
        "variant peptide, proteogenomic state, proteotype, or subtype emission",
        "copy-number-to-protein regression, kinase inference, or all-omics fusion",
        "treatment or clinical recommendation",
        "mutation, relabeling, silent merging, or authority selection over upstream evidence",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0502Request:
    """Issued capability for one exact immutable M05-02 request."""

    request: ReconcilePtmLocalizationIdentityLineageRequest
    _seal: object


_ISSUED_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM0502Request,
        tuple[ReconcilePtmLocalizationIdentityLineageRequest, bytes],
    ]
] = WeakKeyDictionary()


def _token_is_issued(token: ValidatedM0502Request) -> bool:
    snapshot = _ISSUED_TOKENS.get(token)
    try:
        return (
            snapshot is not None
            and snapshot[0] is token.request
            and snapshot[1] == canonical_json_bytes(token.request)
        )
    except Exception:  # noqa: BLE001 - mutated tokens fail closed.
        return False


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-02 execution requires a validated request token")


class M0502Plugin(
    ModulePlugin[
        object,
        ValidatedM0502Request,
        PtmLocalizationIdentityLineageResolution,
    ]
):
    """Grant one immutable M05-02 execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0502Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0502Request:
        candidate = request
        if type(candidate) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", candidate)
            candidate = _strict_json_loads(
                serialized,
                max_bytes=M0502_MAX_CANONICAL_REQUEST_BYTES,
            )
            typed = _validate_json_request(candidate, serialized)
        else:
            typed = self._service.validate_request(candidate)
        token = ValidatedM0502Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_json_bytes(typed))
        return token

    def run(
        self,
        request: ValidatedM0502Request,
    ) -> PtmLocalizationIdentityLineageResolution:
        if (
            type(request) is not ValidatedM0502Request
            or request._seal is not _TOKEN_SEAL
            or not _token_is_issued(request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0502Plugin", "ValidatedM0502Request"]
