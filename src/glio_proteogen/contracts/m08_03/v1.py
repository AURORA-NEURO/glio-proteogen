"""Provisional M08-03 mature baseline estimator contracts.

The M08-03 dossier specifies a transparent baseline, locked preprocessing,
tuning and uncertainty, diagnostics, and safe abstention.  It does not freeze
the operation, request/result names, schema inventory, media type, estimator
implementation, or the M08-02 handoff ABI.  Every symbol here is reviewable
scaffolding and is explicitly provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m08_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from the M08-03 dossier slice.
M0803_MODULE_ID: Final = "GLIO-PROTEOGEN-M08-03"
M0803_OPERATION: Final = "estimate_protein_subtype_baseline"
M0803_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0803_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-03+json"
M0803_M0802_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-02+json"
M0803_PARENT: Final = "protein_subtype"
M0803_OWNER: Final = "Computational biology"
M0803_SAFETY_CLASS: Final = "S2"
M0803_GATE: Final = "G1"
M0803_PROVISIONAL_ABI: Final = True
M0803_MAX_FEATURES: Final = 2_048
M0803_MAX_DIAGNOSTICS: Final = 128
M0803_MAX_FINDINGS: Final = 64
M0803_MAX_EVIDENCE: Final = 64
M0803_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0803_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0803_EVIDENCE_CLAIM: Final = (
    "Caller-declared M08-03 baseline evidence; issuer authority is not authenticated."
)


class BaselineMethod(StrEnum):
    STATISTICAL_RULE_BASED = "statistical_rule_based"
    PATHWAY_ACTIVITY_NETWORK = "pathway_activity_network"
    SELECTIVE_ENSEMBLE_COMPLEX_GRAPH = "selective_ensemble_complex_graph"


class BaselineEstimateStatus(StrEnum):
    ESTIMATED = "estimated"
    ABSTAINED = "abstained"


class BaselineDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class BaselineFindingCode(StrEnum):
    INCOMPLETE_INPUTS = "incomplete_inputs"
    QUALITY_FAILED = "quality_failed"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    CALIBRATION_NOT_LOCKED = "calibration_not_locked"
    OUT_OF_DOMAIN = "out_of_domain"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class BaselineDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: BaselineDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0803_MAX_EVIDENCE)


class BaselineRunConfiguration(FrozenModel):
    """Locked preprocessing, tuning, uncertainty and benchmark declarations."""

    configuration_id: Identifier
    version: SemanticVersion
    method: BaselineMethod
    preprocessing_artifact: ArtifactReference
    tuning_artifact: ArtifactReference
    uncertainty_artifact: ArtifactReference
    benchmark_artifact: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0803_MAX_EVIDENCE)


class ProteinSubtypeBaselineEstimate(FrozenModel):
    """Transparent categorical baseline estimate; no treatment recommendation."""

    predicted_subtype: NonEmptyStr
    score: float = Field(ge=0.0, le=1.0)
    calibration_reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0803_MAX_EVIDENCE)


class EstimateProteinSubtypeBaselineRequest(FrozenModel):
    """Provisional request ABI bound to the M08-02 representation artifact."""

    operation: Literal["estimate_protein_subtype_baseline"] = M0803_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0803_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    representation_result: ArtifactReference
    configuration: BaselineRunConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0803_MAX_FEATURES
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateProteinSubtypeBaselineRequest:
        if self.representation_result.media_type != M0803_M0802_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M08-02 representation result")
        artifact_keys = tuple(
            (artifact.artifact_id, artifact.version, artifact.digest, artifact.media_type)
            for artifact in self.source_artifacts
        )
        if len(artifact_keys) != len(set(artifact_keys)):
            raise ValueError("source artifact references must be unique")
        return self


class ProteinSubtypeBaselineResult(FrozenModel):
    """Baseline output carrying diagnostics, uncertainty, and safe status."""

    output_type: Literal["protein_subtype_baseline_estimate"] = "protein_subtype_baseline_estimate"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0803_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateProteinSubtypeBaselineRequest
    status: BaselineEstimateStatus
    estimate: ProteinSubtypeBaselineEstimate | None = None
    diagnostics: tuple[BaselineDiagnostic, ...] = Field(
        min_length=1, max_length=M0803_MAX_DIAGNOSTICS
    )
    findings: tuple[BaselineFindingCode, ...] = Field(default=(), max_length=M0803_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M0803_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0803_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeBaselineResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        failed_diagnostics = {
            BaselineDiagnosticStatus.FAIL,
            BaselineDiagnosticStatus.NOT_EVALUABLE,
        }
        if self.status is BaselineEstimateStatus.ESTIMATED:
            if (
                self.estimate is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed_diagnostics for item in self.diagnostics)
            ):
                raise ValueError("estimated result requires supported, evaluable baseline output")
        elif (
            self.estimate is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no estimate and explicit safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0803_CONTRACT_VERSION",
    "M0803_EVIDENCE_CLAIM",
    "M0803_GATE",
    "M0803_M0802_RESULT_MEDIA_TYPE",
    "M0803_MAX_CANONICAL_REQUEST_BYTES",
    "M0803_MAX_CANONICAL_RESULT_BYTES",
    "M0803_MAX_DIAGNOSTICS",
    "M0803_MAX_EVIDENCE",
    "M0803_MAX_FEATURES",
    "M0803_MAX_FINDINGS",
    "M0803_MODULE_ID",
    "M0803_OPERATION",
    "M0803_OUTPUT_MEDIA_TYPE",
    "M0803_OWNER",
    "M0803_PARENT",
    "M0803_PROVISIONAL_ABI",
    "M0803_SAFETY_CLASS",
    "BaselineDiagnostic",
    "BaselineDiagnosticStatus",
    "BaselineEstimateStatus",
    "BaselineFindingCode",
    "BaselineMethod",
    "BaselineRunConfiguration",
    "EstimateProteinSubtypeBaselineRequest",
    "ProteinSubtypeBaselineEstimate",
    "ProteinSubtypeBaselineResult",
]
