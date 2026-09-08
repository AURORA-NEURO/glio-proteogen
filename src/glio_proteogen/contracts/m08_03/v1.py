"""Provisional M08-03 mature baseline estimator contracts.

The M08-03 dossier specifies a transparent baseline, locked preprocessing,
tuning and uncertainty, diagnostics, and safe abstention.  It does not freeze
the operation, request/result names, schema inventory, media type, estimator
implementation, or the M08-02 handoff ABI.  Every symbol here is reviewable
scaffolding and is explicitly provisional.
"""

from __future__ import annotations

import math
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
M0803_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M0803_MAX_BOOTSTRAP_REPLICATES: Final = 256
M0803_GLIOMA_MODEL_FAMILY: Final = "glioma-protein-subtype-signed-program-graph/1.0.0"
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


class BaselineFeatureState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class GliomaEvidenceState(StrEnum):
    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class GliomaProgram(StrEnum):
    RTK_PI3K_AKT_MTOR = "rtk_pi3k_akt_mtor"
    P53_CELL_CYCLE = "p53_cell_cycle"
    IDH_HIF1A = "idh_hif1a"
    MESENCHYMAL = "mesenchymal"
    PROLIFERATION = "proliferation"


class GliomaProgramLabel(StrEnum):
    ACTIVATED = "activated"
    SUPPRESSED = "suppressed"
    NEUTRAL = "neutral"
    INDETERMINATE = "indeterminate"


class TypedBaselineObservation(FrozenModel):
    """Typed glioma program evidence for the research baseline lane."""

    observation_id: Identifier
    program: GliomaProgram
    state: GliomaEvidenceState = GliomaEvidenceState.OBSERVED
    standardized_effect: float | None = None
    standard_error: float | None = Field(default=None, gt=0.0)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    censoring_limit: float | None = None
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1,
        max_length=M0803_MAX_EVIDENCE,
    )

    @model_validator(mode="after")
    def observation_shape_is_closed(self) -> TypedBaselineObservation:
        for name, value in (
            ("standardized_effect", self.standardized_effect),
            ("standard_error", self.standard_error),
            ("quality_weight", self.quality_weight),
            ("censoring_limit", self.censoring_limit),
        ):
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.state is GliomaEvidenceState.OBSERVED:
            if (
                self.standardized_effect is None
                or self.standard_error is None
                or self.censoring_limit is not None
            ):
                raise ValueError("observed program evidence requires effect and standard error")
        elif self.state is GliomaEvidenceState.LEFT_CENSORED:
            if (
                self.censoring_limit is None
                or self.standard_error is None
                or self.standardized_effect is not None
            ):
                raise ValueError("left-censored program evidence requires a limit and error")
        elif any(
            value is not None
            for value in (self.standardized_effect, self.standard_error, self.censoring_limit)
        ):
            raise ValueError("missing or unsupported program evidence cannot carry values")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("program evidence must use the evidence role")
        return self


class TypedProgramState(FrozenModel):
    """Signed latent glioma program state with a bounded uncertainty interval."""

    program: GliomaProgram
    state: float
    lower_bound: float
    upper_bound: float
    label: GliomaProgramLabel
    evidence_count: int = Field(ge=0, le=M0803_MAX_FEATURES)
    stability: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def state_interval_is_closed(self) -> TypedProgramState:
        if not all(
            math.isfinite(value)
            for value in (self.state, self.lower_bound, self.upper_bound, self.stability)
        ):
            raise ValueError("typed program state values must be finite")
        if (
            self.lower_bound > self.upper_bound
            or not self.lower_bound <= self.state <= self.upper_bound
        ):
            raise ValueError("typed program state interval must contain its state")
        if any(abs(value) > 1.0 for value in (self.state, self.lower_bound, self.upper_bound)):
            raise ValueError("typed program state values must be bounded in [-1, 1]")
        return self


class BaselineFeatureObservation(FrozenModel):
    """Caller-declared numeric feature used by the transparent baseline."""

    feature_id: Identifier
    state: BaselineFeatureState
    unit: NonEmptyStr
    value: float | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0803_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_matches_state(self) -> BaselineFeatureObservation:
        if self.state is BaselineFeatureState.OBSERVED and self.value is None:
            raise ValueError("observed baseline feature requires a value")
        if self.state is not BaselineFeatureState.OBSERVED and self.value is not None:
            raise ValueError("non-observed baseline feature cannot carry a value")
        return self


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
    model_family: NonEmptyStr = "provisional-baseline-v1"
    bootstrap_replicates: int = Field(
        default=M0803_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=1,
        le=M0803_MAX_BOOTSTRAP_REPLICATES,
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0803_MAX_EVIDENCE)


class ProteinSubtypeBaselineEstimate(FrozenModel):
    """Transparent categorical baseline estimate; no treatment recommendation."""

    predicted_subtype: NonEmptyStr
    score: float = Field(ge=0.0, le=1.0)
    calibration_reference: ArtifactReference
    model_family: NonEmptyStr | None = None
    program_states: tuple[TypedProgramState, ...] = Field(default=(), max_length=5)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0803_MAX_EVIDENCE)

    @model_validator(mode="after")
    def typed_fields_are_bound(self) -> ProteinSubtypeBaselineEstimate:
        programs = tuple(item.program for item in self.program_states)
        if len(programs) != len(set(programs)):
            raise ValueError("typed program states must have unique programs")
        if self.program_states and self.model_family is None:
            raise ValueError("typed program states require a model family")
        return self


class EstimateProteinSubtypeBaselineRequest(FrozenModel):
    """Provisional request ABI bound to the M08-02 representation artifact."""

    operation: Literal["estimate_protein_subtype_baseline"] = M0803_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0803_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    representation_result: ArtifactReference
    configuration: BaselineRunConfiguration
    features: tuple[BaselineFeatureObservation, ...] = Field(
        default=(), max_length=M0803_MAX_FEATURES
    )
    program_observations: tuple[TypedBaselineObservation, ...] = Field(
        default=(), max_length=M0803_MAX_FEATURES
    )
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
        feature_ids = tuple(feature.feature_id for feature in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("baseline feature ids must be unique")
        observation_ids = tuple(item.observation_id for item in self.program_observations)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("typed program observation ids must be unique")
        configuration_artifacts = (
            self.configuration.preprocessing_artifact,
            self.configuration.tuning_artifact,
            self.configuration.uncertainty_artifact,
            self.configuration.benchmark_artifact,
        )
        if len({artifact.artifact_id for artifact in configuration_artifacts}) != len(
            configuration_artifacts
        ):
            raise ValueError("baseline configuration artifacts must be distinct")
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
    typed_model: NonEmptyStr | None = None
    solver_iterations: int | None = Field(default=None, ge=0, le=10_000)
    solver_objective: float | None = None
    objective_trace_digest: Sha256Digest | None = None
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeBaselineResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("result diagnostics must have unique identifiers")
        if len(self.findings) != len(set(self.findings)):
            raise ValueError("result findings must be unique")
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
                or self.findings
            ):
                raise ValueError("estimated result requires supported, evaluable baseline output")
        elif (
            self.estimate is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.findings
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no estimate and explicit safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        if self.solver_objective is not None and not math.isfinite(self.solver_objective):
            raise ValueError("solver objective must be finite")
        if self.typed_model is None and any(
            value is not None
            for value in (
                self.solver_iterations,
                self.solver_objective,
                self.objective_trace_digest,
            )
        ):
            raise ValueError("solver diagnostics require a typed model")
        return self


__all__ = [
    "M0803_CONTRACT_VERSION",
    "M0803_DEFAULT_BOOTSTRAP_REPLICATES",
    "M0803_EVIDENCE_CLAIM",
    "M0803_GATE",
    "M0803_GLIOMA_MODEL_FAMILY",
    "M0803_M0802_RESULT_MEDIA_TYPE",
    "M0803_MAX_BOOTSTRAP_REPLICATES",
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
    "BaselineFeatureObservation",
    "BaselineFeatureState",
    "BaselineFindingCode",
    "BaselineMethod",
    "BaselineRunConfiguration",
    "EstimateProteinSubtypeBaselineRequest",
    "GliomaEvidenceState",
    "GliomaProgram",
    "GliomaProgramLabel",
    "ProteinSubtypeBaselineEstimate",
    "ProteinSubtypeBaselineResult",
    "TypedBaselineObservation",
    "TypedProgramState",
]
