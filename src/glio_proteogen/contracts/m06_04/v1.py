"""Provisional M06-04 probabilistic/advanced estimator contracts.

The dossier freezes the estimator responsibility and safety boundary, but not
its public ABI, posterior representation, feature catalogue, metric set, or
capacity limits.  Every symbol here is scaffolding pending contract review.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m06_01.canonical import canonical_request_digest
from glio_proteogen.contracts.m06_01.v1 import (
    FormalProteinStateSchema,  # noqa: TC001
    FormalStateFeatureValue,  # noqa: TC001
)
from glio_proteogen.contracts.m06_04.canonical import result_payload_digest
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

M0604_MODULE_ID: Final = "GLIO-PROTEOGEN-M06-04"
M0604_OPERATION: Final = "estimate_protein_abundance_probabilistic"
M0604_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0604_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m06-04+json"
M0604_PARENT: Final = "biomarker_panel"
M0604_OWNER: Final = "Scientific engineering"
M0604_SAFETY_CLASS: Final = "S2"
M0604_GATE: Final = "G2"
M0604_PROVISIONAL_ABI: Final = True

# Provisional capacities only; no benchmark or release promise is implied.
M0604_MAX_FEATURES: Final = 512
M0604_MAX_ESTIMATES: Final = M0604_MAX_FEATURES
M0604_MAX_DIAGNOSTICS: Final = 512
M0604_MAX_PRIORS: Final = 128
M0604_MAX_CONSTRAINTS: Final = 128
M0604_MAX_EVIDENCE: Final = 32
M0604_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0604_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0604_EVIDENCE_CLAIM: Final = (
    "Caller-declared probabilistic-estimator evidence; issuer authority is not authenticated."
)


class ProbabilisticEstimatorFamily(StrEnum):
    LEARNED = "probabilistic_learned"
    MECHANISM_GUIDED = "mechanism_guided"
    PROTEOFORM_PROBABILISTIC = "proteoform_probabilistic"


class ProbabilisticPriorKind(StrEnum):
    EMPIRICAL = "empirical"
    NORMAL = "normal"
    LOG_NORMAL = "log_normal"
    CATEGORICAL = "categorical"


class PosteriorEstimateKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"


class OptimizationDiagnosticStatus(StrEnum):
    CONVERGED = "converged"
    NOT_CONVERGED = "not_converged"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class ProbabilisticResultStatus(StrEnum):
    ESTIMATED = "estimated"
    ABSTAINED = "abstained"


class ProbabilisticPrior(FrozenModel):
    prior_id: Identifier
    version: SemanticVersion
    kind: ProbabilisticPriorKind
    parameters: tuple[float, ...] = Field(min_length=1, max_length=32)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0604_MAX_EVIDENCE)


class EstimatorConstraint(FrozenModel):
    constraint_id: Identifier
    expression: NonEmptyStr
    hard: bool
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0604_MAX_EVIDENCE)


class ProbabilisticEstimatorConfiguration(FrozenModel):
    """Versioned priors/constraints/optimization declaration; execution is external."""

    configuration_id: Identifier
    version: SemanticVersion
    estimator_family: ProbabilisticEstimatorFamily
    state_schema_id: Identifier
    state_schema_version: SemanticVersion
    objective: NonEmptyStr
    priors: tuple[ProbabilisticPrior, ...] = Field(
        min_length=1, max_length=M0604_MAX_PRIORS
    )
    constraints: tuple[EstimatorConstraint, ...] = Field(
        default=(), max_length=M0604_MAX_CONSTRAINTS
    )
    optimizer: NonEmptyStr
    seed: int = Field(ge=0)
    max_iterations: int = Field(gt=0, le=10_000_000)
    reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0604_MAX_EVIDENCE)

    @model_validator(mode="after")
    def configuration_ids_are_unique(self) -> ProbabilisticEstimatorConfiguration:
        if len({item.prior_id for item in self.priors}) != len(self.priors):
            raise ValueError("probabilistic prior ids must be unique")
        if len({item.constraint_id for item in self.constraints}) != len(self.constraints):
            raise ValueError("estimator constraint ids must be unique")
        return self


class PosteriorEstimate(FrozenModel):
    feature_id: Identifier
    kind: PosteriorEstimateKind
    unit: NonEmptyStr
    estimate_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    category: NonEmptyStr | None = None
    posterior_mass: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0604_MAX_EVIDENCE)

    @model_validator(mode="after")
    def posterior_shape_is_closed(self) -> PosteriorEstimate:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        if self.kind is PosteriorEstimateKind.SCALAR:
            if self.estimate_value is None or has_interval or self.category is not None:
                raise ValueError("scalar posterior requires one scalar value")
        elif self.kind is PosteriorEstimateKind.INTERVAL:
            if (
                self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or self.estimate_value is None
                or self.category is not None
                or not self.lower_bound <= self.estimate_value <= self.upper_bound
            ):
                raise ValueError("interval posterior requires ordered bounds and center")
        elif self.category is None or self.estimate_value is not None or has_interval:
            raise ValueError("categorical posterior requires only a category")
        return self


class OptimizationDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: OptimizationDiagnosticStatus
    objective: NonEmptyStr
    iteration_count: int = Field(ge=0)
    objective_value: float | None = None
    convergence_gap: float | None = Field(default=None, ge=0.0)
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0604_MAX_EVIDENCE)


class EstimateProteinAbundanceProbabilisticRequest(FrozenModel):
    """Provisional request for posterior estimation from a locked representation."""

    operation: Literal["estimate_protein_abundance_probabilistic"] = M0604_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0604_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    state_schema: FormalProteinStateSchema
    feature_values: tuple[FormalStateFeatureValue, ...] = Field(
        min_length=1, max_length=M0604_MAX_FEATURES
    )
    representation_artifact: ArtifactReference
    baseline_result_digest: Sha256Digest | None = None
    configuration: ProbabilisticEstimatorConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0604_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateProteinAbundanceProbabilisticRequest:
        schema_features = {item.feature_id for item in self.state_schema.features}
        value_features = {item.feature_id for item in self.feature_values}
        if len(value_features) != len(self.feature_values):
            raise ValueError("probabilistic feature values must be unique")
        if value_features != schema_features:
            raise ValueError("probabilistic request must cover the formal-state schema")
        if (
            self.configuration.state_schema_id != self.state_schema.schema_id
            or self.configuration.state_schema_version != self.state_schema.version
        ):
            raise ValueError("probabilistic configuration does not bind the state schema")
        return self


class EstimateProteinAbundanceProbabilisticResult(FrozenModel):
    """Provisional posterior result with diagnostics and explicit abstention."""

    output_type: Literal["protein_abundance_posterior"] = "protein_abundance_posterior"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0604_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateProteinAbundanceProbabilisticRequest
    status: ProbabilisticResultStatus
    estimates: tuple[PosteriorEstimate, ...] = Field(
        default=(), max_length=M0604_MAX_ESTIMATES
    )
    diagnostics: tuple[OptimizationDiagnostic, ...] = Field(
        default=(), max_length=M0604_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker_panel"] = M0604_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0604_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> EstimateProteinAbundanceProbabilisticResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is ProbabilisticResultStatus.ESTIMATED:
            if not self.estimates or self.abstention_reason is not None:
                raise ValueError("estimated result requires posterior estimates")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("estimated result requires supported status")
        elif (
            self.estimates
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no estimates and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0604_CONTRACT_VERSION",
    "M0604_EVIDENCE_CLAIM",
    "M0604_GATE",
    "M0604_MAX_CANONICAL_REQUEST_BYTES",
    "M0604_MAX_CANONICAL_RESULT_BYTES",
    "M0604_MAX_CONSTRAINTS",
    "M0604_MAX_DIAGNOSTICS",
    "M0604_MAX_ESTIMATES",
    "M0604_MAX_EVIDENCE",
    "M0604_MAX_FEATURES",
    "M0604_MAX_PRIORS",
    "M0604_MODULE_ID",
    "M0604_OPERATION",
    "M0604_OUTPUT_MEDIA_TYPE",
    "M0604_OWNER",
    "M0604_PARENT",
    "M0604_PROVISIONAL_ABI",
    "M0604_SAFETY_CLASS",
    "EstimateProteinAbundanceProbabilisticRequest",
    "EstimateProteinAbundanceProbabilisticResult",
    "EstimatorConstraint",
    "OptimizationDiagnostic",
    "OptimizationDiagnosticStatus",
    "PosteriorEstimate",
    "PosteriorEstimateKind",
    "ProbabilisticEstimatorConfiguration",
    "ProbabilisticEstimatorFamily",
    "ProbabilisticPrior",
    "ProbabilisticPriorKind",
    "ProbabilisticResultStatus",
]
