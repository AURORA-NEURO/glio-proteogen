"""Thin stateless M02-02 identity-binding service."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_02 import (
    IdentityBindingEvaluation,
    ValidateIdentityBindingsRequest,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage.engine import (
    M0202IdentityBindingEvaluator,
    preflight_identity_binding_authorization,
)

_REQUEST_ADAPTER: Final[TypeAdapter[ValidateIdentityBindingsRequest]] = TypeAdapter(
    ValidateIdentityBindingsRequest
)


class M0202Service:
    """Preflight, strictly revalidate, and audit one request."""

    __slots__ = ("_evaluator",)

    def __init__(self, evaluator: M0202IdentityBindingEvaluator | None = None) -> None:
        self._evaluator = evaluator or M0202IdentityBindingEvaluator()

    @staticmethod
    def validate_request(request: object) -> ValidateIdentityBindingsRequest:
        preflight_identity_binding_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> IdentityBindingEvaluation:
        return self._evaluator.evaluate(self.validate_request(request))


__all__ = ["M0202Service"]
