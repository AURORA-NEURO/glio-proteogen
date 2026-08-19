"""Strict service seam for M26-06 security evaluation and replay."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_06 import (
    EvaluateProteomicsSecurityAccessRequest,
    ProteomicsSecurityAccessResult,
)

from .engine import (
    M2606ReplayError,
    M2606SecurityEngine,
    M2606ValidatedRequestError,
    preflight_m2606_authorization,
    verify_security_access_result,
)

_REQUEST_ADAPTER: Final[TypeAdapter[EvaluateProteomicsSecurityAccessRequest]] = TypeAdapter(
    EvaluateProteomicsSecurityAccessRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteomicsSecurityAccessResult]] = TypeAdapter(
    ProteomicsSecurityAccessResult
)


class M2606SecurityService:
    """Validate, evaluate, and replay one M26-06 request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2606SecurityEngine | None = None) -> None:
        self._engine = engine or M2606SecurityEngine()

    @staticmethod
    def validate_request(request: object) -> EvaluateProteomicsSecurityAccessRequest:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2606_authorization(validated)
        return validated

    def execute(self, request: object) -> ProteomicsSecurityAccessResult:
        if type(request) is EvaluateProteomicsSecurityAccessRequest:
            return self._execute_validated(request)
        return self._execute_validated(self.validate_request(request))

    def _execute_validated(
        self, request: EvaluateProteomicsSecurityAccessRequest
    ) -> ProteomicsSecurityAccessResult:
        if type(request) is not EvaluateProteomicsSecurityAccessRequest:
            raise M2606ValidatedRequestError
        preflight_m2606_authorization(request)
        return self._engine._evaluate_validated(request)

    @staticmethod
    def verify(result: object) -> ProteomicsSecurityAccessResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except ValidationError as error:
            raise M2606ReplayError from error
        return verify_security_access_result(validated)


__all__ = ["M2606SecurityService"]
