"""Strict plugin boundary for provisional M24-06 robustness challenges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_06 import (
    M2406_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelRobustnessChallengeResult,
    ChallengeBiomarkerPanelRobustnessRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2406_authorization

if TYPE_CHECKING:
    from .service import M2406Service

_ADAPTER: Final = TypeAdapter(ChallengeBiomarkerPanelRobustnessRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M24-06",
    title="Robustness and OOD challenge surface (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "clinical or biological probability",
        "protein/proteoform/isoform or glioma inference",
        "treatment, kinase, identity or consent inference",
        "unsupported-to-negative conversion",
    ),
)


@dataclass(frozen=True, slots=True)
class RobustnessSubmission:
    request: object


class ValidatedM2406Request:
    """Opaque, instance-bound token for one validated request snapshot."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(self, request: ChallengeBiomarkerPanelRobustnessRequest, seal: object) -> None:
        self.request = request
        self._seal = seal


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2406Request,
        tuple[object, ChallengeBiomarkerPanelRobustnessRequest, str],
    ]
] = WeakKeyDictionary()


class M2406Plugin(
    ModulePlugin[object, ValidatedM2406Request, BiomarkerPanelRobustnessChallengeResult]
):
    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2406Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2406Request:
        if not isinstance(request, RobustnessSubmission):
            raise TypeError("M24-06 validation requires a robustness submission")  # noqa: TRY003
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2406_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2406_authorization(decoded)
            candidate = _ADAPTER.validate_json(candidate, strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2406Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_request_digest(validated))
        return token

    def run(self, request: ValidatedM2406Request) -> BiomarkerPanelRobustnessChallengeResult:
        if not isinstance(request, ValidatedM2406Request):
            raise TypeError("M24-06 execution requires a validated request token")  # noqa: TRY003
        snapshot = _TOKENS.get(request)
        if (
            snapshot is None
            or snapshot[0] is not self._seal
            or request._seal is not self._seal
            or snapshot[1] is not request.request
            or snapshot[2] != canonical_request_digest(request.request)
        ):
            raise TypeError("M24-06 execution requires a validated request token")  # noqa: TRY003
        return self._service.evaluate(snapshot[1])

    def replay(
        self, result: BiomarkerPanelRobustnessChallengeResult
    ) -> BiomarkerPanelRobustnessChallengeResult:
        return self._service.verify_replay(result)


__all__ = ["M2406Plugin", "RobustnessSubmission", "ValidatedM2406Request"]
