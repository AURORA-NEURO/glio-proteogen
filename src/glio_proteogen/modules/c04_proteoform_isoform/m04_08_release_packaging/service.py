"""Service facade for the sealed M04-08 release runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
    M0408ProteoformReleaseEngine,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from glio_proteogen.contracts.m04_08 import (
        ProteoformReleaseVerification,
        ProteoformReproducibilityManifest,
    )
    from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging.engine import (
        BuiltProteoformRelease,
        ProteoformSignatureVerifier,
    )


class M0408Service:
    """Stateless local service; executable admission stays sealed until M04-07 freezes."""

    __slots__ = ("_engine",)

    def __init__(self, verifier: ProteoformSignatureVerifier | None = None) -> None:
        self._engine = M0408ProteoformReleaseEngine(verifier)

    def execute(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> BuiltProteoformRelease:
        return self._engine.build(request, artifacts_by_path, stage_results_by_module)

    def manifest(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> ProteoformReproducibilityManifest:
        return self._engine.build_manifest(request, artifacts_by_path, stage_results_by_module)

    def verify(self, result: object, package_bytes: bytes) -> ProteoformReleaseVerification:
        return self._engine.verify(result, package_bytes)


__all__ = ["M0408Service"]
