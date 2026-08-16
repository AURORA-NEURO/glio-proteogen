"""M13-08 service seam for validation, execution, and replay verification."""

from glio_proteogen.contracts.m13_08 import (
    AssembleProteotypeMechanismDossierRequest,
    ProteotypeMechanismDossierResult,
)

from .engine import M1308DossierEngine, preflight_dossier_authorization


class M1308Service:
    """Authorize, strictly validate, assemble, and verify one M13-08 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1308DossierEngine | None = None) -> None:
        self._engine = engine or M1308DossierEngine()

    @staticmethod
    def validate_request(request: object) -> AssembleProteotypeMechanismDossierRequest:
        preflight_dossier_authorization(request)
        return AssembleProteotypeMechanismDossierRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: AssembleProteotypeMechanismDossierRequest,
    ) -> ProteotypeMechanismDossierResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> ProteotypeMechanismDossierResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeMechanismDossierResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1308Service"]
