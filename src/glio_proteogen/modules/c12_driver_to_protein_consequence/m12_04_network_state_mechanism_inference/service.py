"""M12-04 service seam for validation, execution, and replay verification."""

from glio_proteogen.contracts.m12_04 import (
    BiomarkerPanelMechanismInferenceResult,
    InferBiomarkerPanelMechanismRequest,
)

from .engine import M1204MechanismEngine, preflight_mechanism_authorization


class M1204Service:
    """Authorize, strictly validate, infer, and verify one M12-04 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1204MechanismEngine | None = None) -> None:
        self._engine = engine or M1204MechanismEngine()

    @staticmethod
    def validate_request(request: object) -> InferBiomarkerPanelMechanismRequest:
        preflight_mechanism_authorization(request)
        return InferBiomarkerPanelMechanismRequest.model_validate(request, strict=True)

    def _execute_validated(
        self,
        request: InferBiomarkerPanelMechanismRequest,
    ) -> BiomarkerPanelMechanismInferenceResult:
        return self._engine.infer(request)

    def execute(self, request: object) -> BiomarkerPanelMechanismInferenceResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelMechanismInferenceResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1204Service"]
