"""M12-08 service seam for strict validation, execution, and replay."""

from glio_proteogen.contracts.m12_08 import (
    AssembleBiomarkerPanelMechanismDossierRequest,
    BiomarkerPanelMechanismDossierResult,
)

from .engine import M1208MechanismEvidenceEngine, preflight_mechanism_dossier_authorization


class M1208Service:
    """Authorize, strictly validate, assemble, and verify one M12-08 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1208MechanismEvidenceEngine | None = None) -> None:
        self._engine = engine or M1208MechanismEvidenceEngine()

    @staticmethod
    def validate_request(request: object) -> AssembleBiomarkerPanelMechanismDossierRequest:
        preflight_mechanism_dossier_authorization(request)
        return AssembleBiomarkerPanelMechanismDossierRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: AssembleBiomarkerPanelMechanismDossierRequest,
    ) -> BiomarkerPanelMechanismDossierResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> BiomarkerPanelMechanismDossierResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelMechanismDossierResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1208Service"]
