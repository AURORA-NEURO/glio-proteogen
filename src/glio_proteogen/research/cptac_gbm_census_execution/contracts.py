"""Aggregate contracts for additive execution of a byte-locked census baseline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock

PROFILE_ID: Final = "cptac-gbm-census-execution/1.0.0"
BASELINE_PROFILE_ID: Final = "cptac-gbm-source-fit-census/1.0.0"
MAX_BASELINE_DOCUMENT_BYTES: Final = 2 * 1024**2
MAX_ROOT_BYTES: Final = 64 * 1024**2
MAX_PAGE_BYTES: Final = 8 * 1024**2
MAX_PHASE_BYTES: Final = 512 * 1024**2
MAX_FEATURES: Final = 20_000
MAX_CASES: Final = 1_000
EXECUTION_ARTIFACT_NAMES: Final = ("execution-protocol.json", "execution.json")
ROOT_ARTIFACT_NAMES: Final = (
    "protocol.json",
    "source-catalog.json",
    "source-checks.json",
    "external-coverage.json",
    "evaluation.json",
    "progress.json",
    "summary.csv",
)
_PAGE_PATH: Final = re.compile(r"(?:source-fit|external-score)/pages/[0-9]{5}\.json")
_DIGEST: Final = re.compile(r"sha256:[0-9a-f]{64}")


class ExecutionBaselineError(ValueError):
    """Closed, sanitized baseline rejection without source identifiers or paths."""


def require_digest(value: object) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ExecutionBaselineError("a canonical aggregate digest is required")
    return value


def require_integer(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ExecutionBaselineError("an aggregate integer is outside its bound")
    return value


def artifact_limit(name: str) -> int:
    if type(name) is not str:
        raise ExecutionBaselineError("baseline artifact name is outside the closed namespace")
    if name in ("protocol.json", "evaluation.json"):
        return MAX_BASELINE_DOCUMENT_BYTES
    if name in ROOT_ARTIFACT_NAMES:
        return MAX_ROOT_BYTES
    if name in (
        "source-fit/source-census-manifest.json",
        "external-score/manifest.json",
    ) or _PAGE_PATH.fullmatch(name):
        return MAX_PAGE_BYTES
    raise ExecutionBaselineError("baseline artifact name is outside the closed namespace")


@dataclass(frozen=True, slots=True)
class ArtifactBinding:
    relative_path: str
    bytes: int
    sha256: str

    def __post_init__(self) -> None:
        require_integer(self.bytes, minimum=1, maximum=artifact_limit(self.relative_path))
        require_digest(self.sha256)


@dataclass(frozen=True, slots=True)
class BaselineCensusReceipt:
    profile_id: str
    numerical_profile_id: str
    protocol_lock: SourceLock
    evaluation_lock: SourceLock
    numerical_protocol_digest: str
    baseline_report_digest: str
    source_input_protocol_digest: str
    source_fold_assignment_digest: str
    feature_axis_digest: str
    source_manifest_digest: str
    external_manifest_digest: str
    feature_count: int
    source_case_count: int
    external_case_count: int
    source_page_count: int
    external_page_count: int
    artifact_count: int
    artifact_inventory_digest: str
    metadata_locks_authenticate_issuer: bool = False
    baseline_selects_genes_by_outcome: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.profile_id) is not str
            or self.profile_id != PROFILE_ID
            or type(self.numerical_profile_id) is not str
            or self.numerical_profile_id != BASELINE_PROFILE_ID
        ):
            raise ExecutionBaselineError(
                "execution and numerical baseline profiles must remain distinct"
            )
        for lock in (self.protocol_lock, self.evaluation_lock):
            if type(lock) is not SourceLock or lock.bytes > MAX_BASELINE_DOCUMENT_BYTES:
                raise ExecutionBaselineError("baseline document lock exceeds its bound")
        for digest in (
            self.numerical_protocol_digest,
            self.baseline_report_digest,
            self.source_input_protocol_digest,
            self.source_fold_assignment_digest,
            self.feature_axis_digest,
            self.source_manifest_digest,
            self.external_manifest_digest,
            self.artifact_inventory_digest,
        ):
            require_digest(digest)
        require_integer(self.feature_count, minimum=1, maximum=MAX_FEATURES)
        require_integer(self.source_case_count, minimum=60, maximum=MAX_CASES)
        require_integer(self.external_case_count, minimum=1, maximum=MAX_CASES)
        for count in (self.source_page_count, self.external_page_count):
            require_integer(count, minimum=1, maximum=MAX_FEATURES)
        require_integer(self.artifact_count, minimum=11, maximum=2 * MAX_FEATURES + 9)
        if (
            self.artifact_count != 9 + self.source_page_count + self.external_page_count
            or self.metadata_locks_authenticate_issuer is not False
            or self.baseline_selects_genes_by_outcome is not False
        ):
            raise ExecutionBaselineError(
                "baseline inventory and provenance declarations are inconsistent"
            )


__all__ = [
    "BASELINE_PROFILE_ID",
    "EXECUTION_ARTIFACT_NAMES",
    "MAX_BASELINE_DOCUMENT_BYTES",
    "MAX_CASES",
    "MAX_FEATURES",
    "MAX_PAGE_BYTES",
    "MAX_PHASE_BYTES",
    "MAX_ROOT_BYTES",
    "PROFILE_ID",
    "ROOT_ARTIFACT_NAMES",
    "ArtifactBinding",
    "BaselineCensusReceipt",
    "ExecutionBaselineError",
    "artifact_limit",
    "require_digest",
    "require_integer",
]
