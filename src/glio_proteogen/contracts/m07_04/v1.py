"""Provisional M07-04 probabilistic/advanced estimator contracts.

The dossier freezes the estimator responsibility and safety boundary, but not
the public ABI, posterior representation, metric set, or model capacities.
Every symbol here is provisional scaffolding pending owner review.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m07_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
    verify_result_digest,
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

M0704_MODULE_ID: Final = "GLIO-PROTEOGEN-M07-04"
M0704_OPERATION: Final = "estimate_copy_number_dosage_probabilistic"
M0704_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0704_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-04+json"
M0704_REPRESENTATION_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-02+json"
M0704_PARENT: Final = "proteotype"
M0704_OWNER: Final = "Computational biology"
M0704_SAFETY_CLASS: Final = "S2"
M0704_GATE: Final = "G2"
M0704_PROVISIONAL_ABI: Final = True

# Provisional capacities only; no production or benchmark promise is implied.
M0704_MAX_ESTIMATES: Final = 512
M0704_MAX_DIAGNOSTICS: Final = 512
M0704_MAX_PRIORS: Final = 128
M0704_MAX_CONSTRAINTS: Final = 128
M0704_MAX_OBSERVATIONS: Final = 512
M0704_MAX_EVIDENCE: Final = 32
M0704_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0704_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0704_EVIDENCE_CLAIM: Final = (
    "Caller-declared M07-02 representation and probabilistic-estimator evidence; "
    "issuer authority is not authenticated."
)


class ProbabilisticEstimatorFamily(StrEnum):
    LEARNED = "probabilistic_learned"
    MECHANISM_GUIDED = "mechanism_guided"
    VARIANT_PEPTIDE_GRAPH = "variant_peptide_graph"


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
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class EstimatorObservation(FrozenModel):
    """One caller-declared numeric/categorical observation for the proxy.

    The module never opens the referenced artifact.  The digest is retained so
    the observation can be audited and replayed without treating a caller
    declaration as authenticated evidence.
    """

    observation_id: Identifier
    feature_id: Identifier
    unit: NonEmptyStr
    source_artifact_digest: Sha256Digest
    scalar_value: float | None = None
    interval_lower: float | None = None
    interval_upper: float | None = None
    category: NonEmptyStr | None = None

    @model_validator(mode="after")
    def observation_shape_is_closed(self) -> EstimatorObservation:
        interval_present = self.interval_lower is not None or self.interval_upper is not None
        scalar = self.scalar_value is not None
        categorical = self.category is not None
        if sum((scalar, interval_present, categorical)) != 1:
            raise ValueError("observation must contain exactly one scalar, interval, or category")
        if interval_present and (
            self.interval_lower is None
            or self.interval_upper is None
            or self.interval_lower > self.interval_upper
        ):
            raise ValueError("observation interval must have ordered finite bounds")
        numbers = tuple(
            value
            for value in (self.scalar_value, self.interval_lower, self.interval_upper)
            if value is not None
        )
        if any(not isfinite(value) for value in numbers):
            raise ValueError("observation numeric values must be finite")
        return self


class ProbabilisticPrior(FrozenModel):
    prior_id: Identifier
    version: SemanticVersion
    kind: ProbabilisticPriorKind
    parameters: tuple[float, ...] = Field(min_length=1, max_length=32)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0704_MAX_EVIDENCE)


class EstimatorConstraint(FrozenModel):
    constraint_id: Identifier
    expression: NonEmptyStr
    hard: bool
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0704_MAX_EVIDENCE)


class ProbabilisticEstimatorConfiguration(FrozenModel):
    """Versioned priors/constraints declaration; execution is external."""

    configuration_id: Identifier
    version: SemanticVersion
    estimator_family: ProbabilisticEstimatorFamily
    representation_media_type: Literal["application/vnd.glio-proteogen.m07-02+json"] = (
        M0704_REPRESENTATION_MEDIA_TYPE
    )
    objective: NonEmptyStr
    priors: tuple[ProbabilisticPrior, ...] = Field(min_length=1, max_length=M0704_MAX_PRIORS)
    constraints: tuple[EstimatorConstraint, ...] = Field(
        default=(), max_length=M0704_MAX_CONSTRAINTS
    )
    optimizer: NonEmptyStr
    seed: int = Field(ge=0)
    max_iterations: int = Field(gt=0, le=10_000_000)
    reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0704_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0704_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0704_MAX_EVIDENCE)


class EstimateCopyNumberDosageProbabilisticRequest(FrozenModel):
    """Provisional request bound to M07-02 representation and M07-03 baseline."""

    operation: Literal["estimate_copy_number_dosage_probabilistic"] = M0704_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0704_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    representation_result: ArtifactReference
    baseline_result_digest: Sha256Digest
    configuration: ProbabilisticEstimatorConfiguration
    observations: tuple[EstimatorObservation, ...] = Field(
        min_length=1, max_length=M0704_MAX_OBSERVATIONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0704_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateCopyNumberDosageProbabilisticRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("request id must match execution context request id")
        if self.representation_result.media_type != M0704_REPRESENTATION_MEDIA_TYPE:
            raise ValueError(
                "probabilistic request must bind the provisional M07-02 representation"
            )
        if self.configuration.representation_media_type != self.representation_result.media_type:
            raise ValueError("configuration does not bind the M07-02 representation")
        if self.configuration.reference != self.representation_result:
            raise ValueError("configuration reference must equal the representation reference")
        artifact_digests = {
            self.representation_result.digest,
            *(artifact.digest for artifact in self.source_artifacts),
        }
        if any(item.source_artifact_digest not in artifact_digests for item in self.observations):
            raise ValueError("observation source digest must name a declared artifact")
        if len({item.observation_id for item in self.observations}) != len(self.observations):
            raise ValueError("observation ids must be unique")
        if len({item.artifact_id for item in self.source_artifacts}) != len(self.source_artifacts):
            raise ValueError("source artifact ids must be unique")
        return self


class EstimateCopyNumberDosageProbabilisticResult(FrozenModel):
    """Provisional posterior result with diagnostics, uncertainty, and safe failure."""

    output_type: Literal["copy_number_dosage_posterior"] = "copy_number_dosage_posterior"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0704_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateCopyNumberDosageProbabilisticRequest
    status: ProbabilisticResultStatus
    estimates: tuple[PosteriorEstimate, ...] = Field(default=(), max_length=M0704_MAX_ESTIMATES)
    diagnostics: tuple[OptimizationDiagnostic, ...] = Field(
        default=(), max_length=M0704_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M0704_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0704_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> EstimateCopyNumberDosageProbabilisticResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != f"result.{self.request_digest.removeprefix('sha256:')}":
            raise ValueError("result id must be deterministic from request digest")
        if not self.evidence:
            raise ValueError("result requires explicit source evidence")
        if len({item.feature_id for item in self.estimates}) != len(self.estimates):
            raise ValueError("result estimates must have unique feature ids")
        if len({item.diagnostic_id for item in self.diagnostics}) != len(self.diagnostics):
            raise ValueError("result diagnostics must have unique ids")
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
            raise ValueError("non-estimated result requires no estimates and safe status")
        if self.status is not ProbabilisticResultStatus.ESTIMATED and not self.human_review_required:
            raise ValueError("abstained or quarantined result requires human review")
        if self.result_digest != result_payload_digest(self) or not verify_result_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Make every uncertainty dimension explicit until calibration is frozen."""

    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M07-04 calibration and model registry are not frozen; no probability is claimed.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Deterministic proxy intervals are not calibrated posterior intervals.",
        ),
    )


__all__ = [
    "M0704_CONTRACT_VERSION",
    "M0704_EVIDENCE_CLAIM",
    "M0704_GATE",
    "M0704_MAX_CANONICAL_REQUEST_BYTES",
    "M0704_MAX_CANONICAL_RESULT_BYTES",
    "M0704_MAX_CONSTRAINTS",
    "M0704_MAX_DIAGNOSTICS",
    "M0704_MAX_ESTIMATES",
    "M0704_MAX_EVIDENCE",
    "M0704_MAX_OBSERVATIONS",
    "M0704_MODULE_ID",
    "M0704_OPERATION",
    "M0704_OUTPUT_MEDIA_TYPE",
    "M0704_OWNER",
    "M0704_PARENT",
    "M0704_PROVISIONAL_ABI",
    "M0704_REPRESENTATION_MEDIA_TYPE",
    "M0704_SAFETY_CLASS",
    "EstimateCopyNumberDosageProbabilisticRequest",
    "EstimateCopyNumberDosageProbabilisticResult",
    "EstimatorConstraint",
    "EstimatorObservation",
    "OptimizationDiagnostic",
    "OptimizationDiagnosticStatus",
    "PosteriorEstimate",
    "PosteriorEstimateKind",
    "ProbabilisticEstimatorConfiguration",
    "ProbabilisticEstimatorFamily",
    "ProbabilisticPrior",
    "ProbabilisticPriorKind",
    "ProbabilisticResultStatus",
    "expected_uncertainty",
]
