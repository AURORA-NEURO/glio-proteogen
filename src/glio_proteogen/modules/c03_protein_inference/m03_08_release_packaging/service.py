"""Stateless application boundary for M03-08 protein-inference releases."""

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_08 import (
    BuildProteinInferenceReleaseRequest,
    ProteinInferenceReleaseVerification,
    ProteinInferenceReproducibilityManifest,
)
from glio_proteogen.modules.c03_protein_inference.m03_08_release_packaging.engine import (
    BuiltProteinInferenceRelease,
    M0308ProteinInferenceReleaseEngine,
    ProteinInferenceSignatureVerifier,
    preflight_protein_inference_release_authorization,
)

_REQUEST_ADAPTER = TypeAdapter(BuildProteinInferenceReleaseRequest)


class M0308Service:
    """Authorize, validate, package, and inspect without owning signing keys."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        verifier: ProteinInferenceSignatureVerifier | None = None,
        engine: M0308ProteinInferenceReleaseEngine | None = None,
    ) -> None:
        self._engine = engine or M0308ProteinInferenceReleaseEngine(verifier)

    @staticmethod
    def validate_request(request: object) -> BuildProteinInferenceReleaseRequest:
        preflight_protein_inference_release_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def build(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> BuiltProteinInferenceRelease:
        return self._engine.build(request, artifacts_by_path, stage_results_by_module)

    def build_manifest(
        self,
        request: object,
        artifacts_by_path: Mapping[str, object],
        stage_results_by_module: Mapping[str, object],
    ) -> ProteinInferenceReproducibilityManifest:
        return self._engine.build_manifest(
            request,
            artifacts_by_path,
            stage_results_by_module,
        )

    def verify(
        self,
        result: object,
        package_bytes: bytes,
    ) -> ProteinInferenceReleaseVerification:
        return self._engine.verify(result, package_bytes)


__all__ = ["M0308Service"]
