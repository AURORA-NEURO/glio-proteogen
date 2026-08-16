"""Provisional M09-03 mature baseline estimator contracts.

The M09-03 dossier specifies a transparent baseline, locked preprocessing,
tuning and uncertainty, diagnostics, and safe abstention.  It does not freeze
the operation, request/result names, schema inventory, media type, estimator
implementation, or the M09-02 handoff ABI.  Every symbol here is reviewable
scaffolding and is explicitly provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from glio_proteogen.contracts.m09_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M09-03 dossier slice.
M0903_MODULE_ID: Final = "GLIO-PROTEOGEN-M09-03"
M0903_OPERATION: Final = "estimate_complex_activity_baseline"
M0903_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0903_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-03+json"
M0903_M0902_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-02+json"
M0903_PARENT: Final = "complex_activity"
M0903_OWNER: Final = "Bioinformatics"
M0903_SAFETY_CLASS: Final = "S2"
M0903_GATE: Final = "G1"
M0903_PROVISIONAL_ABI: Final = True
M0903_MAX_FEATURES: Final = 2_048
M0903_MAX_DIAGNOSTICS: Final = 128
M0903_MAX_FINDINGS: Final = 64
M0903_MAX_EVIDENCE: Final = 64
M0903_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0903_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0903_EVIDENCE_CLAIM: Final = (
    "Caller-declared M09-03 baseline evidence; issuer authority is not authenticated."
)


class BaselineMethod(StrEnum):
    STATISTICAL_RULE_BASED = "statistical_rule_based"
    STOICHIOMETRIC_FACTORIZATION = "stoichiometric_factorization"
    SELECTIVE_ENSEMBLE_PATHWAY_NETWORK = "selective_ensemble_pathway_network"


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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0903_MAX_EVIDENCE)

    @field_validator("message")
    @classmethod
    def diagnostic_message_is_actionable(cls, value: NonEmptyStr) -> NonEmptyStr:
        if value.casefold().startswith(("todo", "tbd", "placeholder")):
            raise ValueError("diagnostic message must be an actionable declaration")
        return value


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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0903_MAX_EVIDENCE)

    @model_validator(mode="after")
    def configuration_is_complete(self) -> BaselineRunConfiguration:
        artifacts = (
            self.preprocessing_artifact,
            self.tuning_artifact,
            self.uncertainty_artifact,
            self.benchmark_artifact,
        )
        artifact_ids = tuple(item.artifact_id for item in artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("baseline configuration artifacts must have distinct identities")
        if not self.evidence:
            raise ValueError("locked baseline configuration requires evidence references")
        return self


class ComplexActivityBaselineEstimate(FrozenModel):
    """Transparent categorical baseline estimate; no treatment recommendation."""

    predicted_activity: NonEmptyStr
    score: float = Field(ge=0.0, le=1.0)
    calibration_reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0903_MAX_EVIDENCE)

    @field_validator("predicted_activity")
    @classmethod
    def estimate_is_not_a_prohibited_claim(cls, value: NonEmptyStr) -> NonEmptyStr:
        prohibited = ("kinase", "treatment", "therapy", "all_omics", "subtype")
        if any(marker in value.casefold() for marker in prohibited):
            raise ValueError("baseline estimate cannot emit prohibited ownership claims")
        return value


class EstimateComplexActivityBaselineRequest(FrozenModel):
    """Provisional request ABI bound to the M09-02 representation artifact."""

    operation: Literal["estimate_complex_activity_baseline"] = M0903_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0903_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    representation_result: ArtifactReference
    configuration: BaselineRunConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0903_MAX_FEATURES
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateComplexActivityBaselineRequest:
        if self.representation_result.media_type != M0903_M0902_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M09-02 representation result")
        artifact_keys = tuple(
            (artifact.artifact_id, artifact.version, artifact.digest, artifact.media_type)
            for artifact in self.source_artifacts
        )
        if len(artifact_keys) != len(set(artifact_keys)):
            raise ValueError("source artifact references must be unique")
        if any(
            artifact.artifact_id == self.representation_result.artifact_id
            for artifact in self.source_artifacts
        ):
            raise ValueError("representation handoff must not be duplicated as a source artifact")
        return self


class ComplexActivityBaselineResult(FrozenModel):
    """Baseline output carrying diagnostics, uncertainty, and safe status."""

    output_type: Literal["complex_activity_baseline_estimate"] = (
        "complex_activity_baseline_estimate"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0903_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateComplexActivityBaselineRequest
    status: BaselineEstimateStatus
    estimate: ComplexActivityBaselineEstimate | None = None
    diagnostics: tuple[BaselineDiagnostic, ...] = Field(
        min_length=1, max_length=M0903_MAX_DIAGNOSTICS
    )
    findings: tuple[BaselineFindingCode, ...] = Field(default=(), max_length=M0903_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M0903_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0903_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityBaselineResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        failed_diagnostics = {
            BaselineDiagnosticStatus.FAIL,
            BaselineDiagnosticStatus.NOT_EVALUABLE,
        }
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("baseline diagnostic ids must be unique")
        finding_set = set(self.findings)
        if self.status is BaselineEstimateStatus.ESTIMATED:
            if (
                self.estimate is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed_diagnostics for item in self.diagnostics)
                or finding_set
                & {
                    BaselineFindingCode.INCOMPLETE_INPUTS,
                    BaselineFindingCode.QUALITY_FAILED,
                    BaselineFindingCode.UPSTREAM_UNSUPPORTED,
                    BaselineFindingCode.CALIBRATION_NOT_LOCKED,
                    BaselineFindingCode.OUT_OF_DOMAIN,
                }
            ):
                raise ValueError("estimated result requires supported, evaluable baseline output")
        elif (
            self.estimate is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not finding_set
        ):
            raise ValueError("abstained result requires no estimate and explicit safe status")
        if (
            self.support_decision.status is SupportStatus.REVIEW_REQUIRED
            and not self.human_review_required
        ):
            raise ValueError("review-required baseline result must request human review")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0903_CONTRACT_VERSION",
    "M0903_EVIDENCE_CLAIM",
    "M0903_GATE",
    "M0903_M0902_RESULT_MEDIA_TYPE",
    "M0903_MAX_CANONICAL_REQUEST_BYTES",
    "M0903_MAX_CANONICAL_RESULT_BYTES",
    "M0903_MAX_DIAGNOSTICS",
    "M0903_MAX_EVIDENCE",
    "M0903_MAX_FEATURES",
    "M0903_MAX_FINDINGS",
    "M0903_MODULE_ID",
    "M0903_OPERATION",
    "M0903_OUTPUT_MEDIA_TYPE",
    "M0903_OWNER",
    "M0903_PARENT",
    "M0903_PROVISIONAL_ABI",
    "M0903_SAFETY_CLASS",
    "BaselineDiagnostic",
    "BaselineDiagnosticStatus",
    "BaselineEstimateStatus",
    "BaselineFindingCode",
    "BaselineMethod",
    "BaselineRunConfiguration",
    "ComplexActivityBaselineEstimate",
    "ComplexActivityBaselineResult",
    "EstimateComplexActivityBaselineRequest",
]
