"""Strict parse-once plugin adapter for M22-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_06 import (
    M2206_MAX_CANONICAL_REQUEST_BYTES,
    ChallengeProteinRnaDiscordanceRobustnessRequest,
    ProteinRnaDiscordanceRobustnessChallengeResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2206Engine, preflight_m2206_authorization
from .service import M2206Service

_REQUEST_ADAPTER: Final = TypeAdapter(ChallengeProteinRnaDiscordanceRobustnessRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceRobustnessChallengeResult)
@dataclass(frozen=True, slots=True)
class ValidatedM2206Request:
    """Opaque request token issued by the strict parser."""

    request: ChallengeProteinRnaDiscordanceRobustnessRequest
    _seal: object
    _request_identity: int = 0
    _request_bytes: bytes = b""


class M2206Plugin:
    """Plugin enforcing validation exactly once before challenge execution."""

    def __init__(self, service: M2206Service | None = None) -> None:
        self._service = service or M2206Service(M2206Engine())
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M22-06",
            title="Robustness shift and OOD challenge",
            version="0.1.0-provisional",
            owner="Bioinformatics",
            safety_class="S3",
            gate="G3",
            prohibited_outputs=(
                "protein-RNA discordance estimate",
                "identity or consent inference",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2206Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2206_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2206_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2206_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM2206Request(
            request=typed,
            _seal=self._seal,
            _request_identity=id(typed),
            _request_bytes=canonical_json_bytes(typed.model_dump(mode="json")),
        )

    def run(self, request: ValidatedM2206Request) -> ProteinRnaDiscordanceRobustnessChallengeResult:
        if (
            not isinstance(request, ValidatedM2206Request)
            or request._seal is not self._seal
            or type(request.request) is not ChallengeProteinRnaDiscordanceRobustnessRequest
            or id(request.request) != request._request_identity
        ):
            raise TypeError
        if canonical_json_bytes(request.request.model_dump(mode="json")) != request._request_bytes:
            raise TypeError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceRobustnessChallengeResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result, replay=replay)


__all__ = ["M2206Plugin", "ValidatedM2206Request"]
