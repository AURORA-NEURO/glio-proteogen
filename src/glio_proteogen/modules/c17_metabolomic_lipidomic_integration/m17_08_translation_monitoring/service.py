"""M17-08 translation monitoring service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine import M1708Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m17_08 import (
        MonitorVariantPeptideTranslationHealthRequest,
        VariantPeptideTranslationMonitoringResult,
    )


class M1708Service:
    """Stateless service wrapper for translation health monitoring."""

    def __init__(self) -> None:
        self._engine = M1708Engine()

    def validate_request(self, candidate: object) -> MonitorVariantPeptideTranslationHealthRequest:
        return self._engine.validate_request(candidate)

    def monitor(self, candidate: object) -> VariantPeptideTranslationMonitoringResult:
        return self._engine.adapt(candidate)

    def replay(
        self,
        result: VariantPeptideTranslationMonitoringResult,
    ) -> VariantPeptideTranslationMonitoringResult:
        return self._engine.replay(result)


__all__ = ["M1708Service"]
