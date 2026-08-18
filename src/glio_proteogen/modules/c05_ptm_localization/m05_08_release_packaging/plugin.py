"""Strict validate-then-run plugin for the M05-08 package boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_08 import (
    M0508_CONTRACT_VERSION,
    M0508_MAX_CANONICAL_REQUEST_BYTES,
    M0508_MODULE_ID,
    BuildPtmLocalizationReleaseRequest,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.engine import (
    BuiltPtmLocalizationRelease,
    PtmLocalizationReleaseInputError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.service import (
    M0508Service,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_REQUEST_ADAPTER: Final = TypeAdapter(BuildPtmLocalizationReleaseRequest)

_PROVISIONAL_DESCRIPTOR: Final = {
    "moduleId": M0508_MODULE_ID,
    "title": "PTM-localization provenance and release packaging",
    "version": M0508_CONTRACT_VERSION,
    "status": "provisional",
    "operation": "package_ptm_localization_release",
    "prohibitedOutputs": (
        "kinase_activity",
        "all_omics_fusion",
        "treatment_recommendation",
        "identity_inference",
    ),
}


@dataclass(frozen=True, slots=True)
class PtmLocalizationReleaseSubmission:
    request: object
    artifacts_by_path: Mapping[str, bytes]


@dataclass(frozen=True, slots=True)
class ValidatedM0508Request:
    request: BuildPtmLocalizationReleaseRequest
    artifacts_by_path: Mapping[str, bytes]


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-08 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-08 validation requires a release submission")


class M0508Plugin:
    """Expose M05-08 through a strict, parse-once submission boundary."""

    descriptor = _PROVISIONAL_DESCRIPTOR

    def __init__(self, service: M0508Service | None = None) -> None:
        self._service = service or M0508Service()

    def validate_request(self, request: object) -> BuildPtmLocalizationReleaseRequest:
        return self._service.validate_request(request)

    def validate(self, submission: object) -> ValidatedM0508Request:
        if not isinstance(submission, PtmLocalizationReleaseSubmission):
            raise _InvalidSubmissionError
        candidate = submission.request
        if isinstance(candidate, (bytes, bytearray, str)):
            strict_json_loads(candidate, max_bytes=M0508_MAX_CANONICAL_REQUEST_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0508Request(
            request=self._service.validate_request(candidate),
            artifacts_by_path=submission.artifacts_by_path,
        )

    def run(self, request: ValidatedM0508Request) -> BuiltPtmLocalizationRelease:
        if not isinstance(request, ValidatedM0508Request):
            raise _InvalidExecutionTokenError
        return self._service.build(request.request, request.artifacts_by_path)

    def execute(
        self,
        request: object,
        artifacts_by_path: Mapping[str, bytes] | None = None,
    ) -> BuiltPtmLocalizationRelease:
        if artifacts_by_path is None:
            raise PtmLocalizationReleaseInputError("artifact_map")
        return self._service.execute(request, artifacts_by_path)


__all__ = [
    "M0508Plugin",
    "PtmLocalizationReleaseSubmission",
    "ValidatedM0508Request",
]
