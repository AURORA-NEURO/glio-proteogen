"""Stateless M06-01 service boundary."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_01 import (
    ValidateFormalProteinStateRequest,
    ValidateFormalProteinStateResult,
)
from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema.engine import (
    M0601FormalStateEngine,
    _plain_value,
    preflight_formal_state_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateFormalProteinStateRequest)


class M0601Service:
    """Authorize and strictly validate before executing formal-state invariants."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0601FormalStateEngine | None = None) -> None:
        self._engine = engine or M0601FormalStateEngine()

    @staticmethod
    def validate_request(request: object) -> ValidateFormalProteinStateRequest:
        preflight_formal_state_authorization(request)
        return _REQUEST_ADAPTER.validate_python(_plain_value(request), strict=True)

    def execute(self, request: object) -> ValidateFormalProteinStateResult:
        return self._engine.validate(request)


__all__ = ["M0601Service"]
