"""Sealed M19-03 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m19_03 import canonical_request_bytes

from .engine import M1903Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_03 import (
        FuseProteotypeEvidenceRequest,
        ProteotypeIntegratedEvidenceResult,
    )


@dataclass(frozen=True, slots=True)
class M1903PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-03"
    operation: str = "fuse_proteotype_evidence"
    output_media_type: str = "application/vnd.glio-proteogen.m19-03+json"
    parent_target: str = "proteotype"
    owner: str = "Quality engineering"
    safety_class: str = "S2"
    evidence_gate: str = "G2"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    source_attribution: bool = True
    disagreement_preservation: bool = True
    explicit_abstention: bool = True


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1903Request:
    """Opaque capability proving one plugin-scoped validated request."""

    request: FuseProteotypeEvidenceRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1903Request,
        tuple[object, FuseProteotypeEvidenceRequest, bytes],
    ]
] = WeakKeyDictionary()


def _token_is_issued(token: ValidatedM1903Request, seal: object) -> bool:
    try:
        snapshot = _TOKENS.get(token)
        current = canonical_request_bytes(token.request)
    except (TypeError, ValueError):
        return False
    return (
        snapshot is not None
        and snapshot[0] is seal
        and snapshot[1] is token.request
        and snapshot[2] == current
    )


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M19-03 execution requires a validated request token")


class M1903Plugin:
    """Expose only component-specific fusion and exact replay."""

    descriptor: Final = M1903PluginDescriptor()

    __slots__ = ("_engine", "_seal")

    def __init__(self) -> None:
        self._engine = M1903Engine()
        self._seal = object()

    def validate_request(self, candidate: object) -> FuseProteotypeEvidenceRequest:
        return self._engine.validate_request(candidate)

    def validate(self, candidate: object) -> ValidatedM1903Request:
        """Return an instance-scoped capability for parse-once execution."""

        validated = self._engine.validate_request(candidate)
        token = ValidatedM1903Request(request=validated, _seal=self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_request_bytes(validated))
        return token

    def run(
        self,
        request: FuseProteotypeEvidenceRequest | ValidatedM1903Request,
    ) -> ProteotypeIntegratedEvidenceResult:
        if type(request) is ValidatedM1903Request:
            if (
                request._seal is not self._seal
                or not _token_is_issued(request, self._seal)
            ):
                raise _InvalidExecutionTokenError
            return self._engine.adapt(request.request)
        return self._engine.adapt(request)

    def replay(
        self,
        result: ProteotypeIntegratedEvidenceResult,
    ) -> ProteotypeIntegratedEvidenceResult:
        return self._engine.replay(result)


__all__ = ["M1903Plugin", "M1903PluginDescriptor", "ValidatedM1903Request"]
