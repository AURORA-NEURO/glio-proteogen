"""Sealed M18-03 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1803Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_03 import (
        BiomarkerPanelIntegratedEvidenceResult,
        FuseBiomarkerPanelEvidenceRequest,
    )


@dataclass(frozen=True, slots=True)
class M1803PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M18-03"
    operation: str = "fuse_biomarker_panel_evidence"
    output_media_type: str = "application/vnd.glio-proteogen.m18-03+json"
    parent_target: str = "biomarker panel"
    owner: str = "ML engineering"
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
class ValidatedM1803Request:
    """Opaque capability proving one plugin-scoped validated request."""

    request: FuseBiomarkerPanelEvidenceRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1803Request,
        tuple[object, FuseBiomarkerPanelEvidenceRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: FuseBiomarkerPanelEvidenceRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM1803Request, seal: object) -> bool:
    try:
        snapshot = _TOKENS.get(token)
        current = _canonical_request_bytes(token.request)
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
        super().__init__("M18-03 execution requires a validated request token")


class M1803Plugin:
    """Expose only component-specific fusion and exact replay."""

    __slots__ = ("_engine", "_seal")
    descriptor: Final = M1803PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1803Engine()
        self._seal = object()

    def validate_request(self, candidate: object) -> FuseBiomarkerPanelEvidenceRequest:
        return self._engine.validate_request(candidate)

    def validate(self, candidate: object) -> ValidatedM1803Request:
        """Return an instance-scoped capability for parse-once execution."""

        validated = self._engine.validate_request(candidate)
        token = ValidatedM1803Request(request=validated, _seal=self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(
        self,
        request: FuseBiomarkerPanelEvidenceRequest | ValidatedM1803Request,
    ) -> BiomarkerPanelIntegratedEvidenceResult:
        if type(request) is ValidatedM1803Request:
            if (
                request._seal is not self._seal
                or not _token_is_issued(request, self._seal)
            ):
                raise _InvalidExecutionTokenError
            return self._engine.adapt(request.request)
        return self._engine.adapt(request)

    def replay(
        self,
        result: BiomarkerPanelIntegratedEvidenceResult,
    ) -> BiomarkerPanelIntegratedEvidenceResult:
        return self._engine.replay(result)


__all__ = ["M1803Plugin", "M1803PluginDescriptor", "ValidatedM1803Request"]
