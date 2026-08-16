"""Service seam for the provisional M14-08 runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_08 import PublishProteinSubtypeMechanismDossierRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1408DossierEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m14_08 import ProteinSubtypeMechanismEvidenceDossierResult

_REQUEST_ADAPTER = TypeAdapter(PublishProteinSubtypeMechanismDossierRequest)


class M1408Service:
    """Keep adapter execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1408DossierEngine | None = None) -> None:
        self._engine = engine or M1408DossierEngine()

    def execute(
        self, request: PublishProteinSubtypeMechanismDossierRequest
    ) -> ProteinSubtypeMechanismEvidenceDossierResult:
        return self._engine.infer(request)

    def validate_request(self, request: object) -> PublishProteinSubtypeMechanismDossierRequest:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)

    def _execute_validated(
        self, request: PublishProteinSubtypeMechanismDossierRequest
    ) -> ProteinSubtypeMechanismEvidenceDossierResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeMechanismEvidenceDossierResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1408Service"]
