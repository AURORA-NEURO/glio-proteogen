"""Application service boundary for M11-08."""

from glio_proteogen.contracts.m11_08 import (
    AssembleVariantPeptideMechanismDossierRequest,
    VariantPeptideMechanismDossierResult,
)

from .engine import (
    M1108MechanismEvidenceDossierEngine,
    _validate_authorized_request,
    verify_mechanism_dossier_result,
)


class M1108MechanismEvidenceDossierService:
    """Validate, execute and verify one immutable M11-08 dossier."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1108MechanismEvidenceDossierEngine | None = None) -> None:
        self._engine = engine or M1108MechanismEvidenceDossierEngine()

    @staticmethod
    def validate_request(request: object) -> AssembleVariantPeptideMechanismDossierRequest:
        return _validate_authorized_request(request)

    def execute(self, request: object) -> VariantPeptideMechanismDossierResult:
        return self._engine.assemble(request)

    @staticmethod
    def verify(result: object) -> bool:
        return verify_mechanism_dossier_result(result)


__all__ = ["M1108MechanismEvidenceDossierService"]
