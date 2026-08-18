"""Strict M26-08 service seam for validation, retirement and replay."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_08 import (
    ProteinSubtypeRetirementResult,
    RetireProteinSubtypeServiceRequest,
)

from .engine import (
    M2608ReplayError,
    M2608RetirementEngine,
    preflight_m2608_authorization,
    verify_retirement_result,
)

_REQUEST_ADAPTER: Final[TypeAdapter[RetireProteinSubtypeServiceRequest]] = TypeAdapter(
    RetireProteinSubtypeServiceRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteinSubtypeRetirementResult]] = TypeAdapter(
    ProteinSubtypeRetirementResult
)


class M2608RetirementService:
    """Validate, retire, and replay one M26-08 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2608RetirementEngine | None = None) -> None:
        self._engine = engine or M2608RetirementEngine()

    @staticmethod
    def validate_request(request: object) -> RetireProteinSubtypeServiceRequest:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2608_authorization(validated)
        return validated

    def retire(self, request: object) -> ProteinSubtypeRetirementResult:
        return self._engine.retire(self.validate_request(request))

    @staticmethod
    def verify(result: object) -> ProteinSubtypeRetirementResult:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
            return verify_retirement_result(typed)
        except M2608ReplayError:
            raise
        except (TypeError, ValueError, ValidationError) as error:
            raise M2608ReplayError from error

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M26-08",
            "operation": "retire_protein_subtype_service",
            "owner": "Scientific engineering",
            "safety_class": "S3",
            "gate": "G5",
            "parent": "protein subtype",
            "provisional_abi": True,
            "retirement_criteria": True,
            "dependency_migration": True,
            "evidence_preservation": True,
            "communication_acknowledgement": True,
            "long_term_archive": True,
            "safe_abstention": True,
            "seven_control_preflight": True,
        }


__all__ = ["M2608ReplayError", "M2608RetirementService"]
