"""Stateless application boundary for the provisional M05-08 scaffold."""

from __future__ import annotations

from glio_proteogen.contracts.m05_08 import (
    BuildPtmLocalizationReleaseRequest,
    PtmLocalizationReleaseManifest,
)
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.engine import (
    M0508PtmLocalizationReleaseEngine,
)


class M0508Service:
    """Validate the frozen-shaped boundary without claiming package execution."""

    __slots__ = ("_engine",)

    def __init__(self) -> None:
        self._engine = M0508PtmLocalizationReleaseEngine()

    @staticmethod
    def validate_request(request: object) -> BuildPtmLocalizationReleaseRequest:
        return M0508PtmLocalizationReleaseEngine.validate_request(request)

    def manifest(self, request: object) -> PtmLocalizationReleaseManifest:
        return self._engine.manifest(request)

    def execute(self, request: object) -> None:
        return self._engine.execute(request)


__all__ = ["M0508Service"]
