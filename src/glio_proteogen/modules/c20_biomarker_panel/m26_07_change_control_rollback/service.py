"""Strict M26-07 change-control service seam."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_07 import (
    ControlProteinSubtypeChangeRequest,
    ProteinSubtypeChangeControlResult,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback.engine import (
    M2607ChangeControlEngine,
    M2607ReplayError,
    preflight_m2607_authorization,
    verify_change_control_result,
)

_REQUEST_ADAPTER: Final[TypeAdapter[ControlProteinSubtypeChangeRequest]] = TypeAdapter(
    ControlProteinSubtypeChangeRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteinSubtypeChangeControlResult]] = TypeAdapter(
    ProteinSubtypeChangeControlResult
)


class M2607ChangeControlService:
    """Validate, control, and replay one M26-07 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2607ChangeControlEngine | None = None) -> None:
        self._engine = engine or M2607ChangeControlEngine()

    @staticmethod
    def validate_request(request: object) -> ControlProteinSubtypeChangeRequest:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2607_authorization(validated)
        return validated

    def control(self, request: object) -> ProteinSubtypeChangeControlResult:
        return self._engine.control(self.validate_request(request))

    @staticmethod
    def verify(result: object) -> ProteinSubtypeChangeControlResult:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
            return verify_change_control_result(typed)
        except M2607ReplayError:
            raise
        except (TypeError, ValueError, ValidationError) as error:
            raise M2607ReplayError from error

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M26-07",
            "operation": "control_protein_subtype_change_and_rollback",
            "owner": "Platform engineering",
            "safety_class": "S3",
            "gate": "G5",
            "parent": "protein subtype",
            "provisional_abi": True,
            "change_classification": True,
            "revalidation": True,
            "champion_challenger": True,
            "staged_rollout": True,
            "tested_rollback": True,
        }


__all__ = ["M2607ChangeControlService", "M2607ReplayError"]
