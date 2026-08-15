"""Provisional M08-04 probabilistic/advanced estimator contracts.

The dossier freezes primary inference, diagnostics, seeds, and failure
handling, but not the public ABI, posterior representation, feature handoff,
or model catalogue.  Every symbol below is provisional scaffolding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m08_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
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
    UncertaintyEstimate,
    UncertaintyProfile,
)

M0804_MODULE_ID: Final = "GLIO-PROTEOGEN-M08-04"
M0804_OPERATION: Final = "estimate_transcript_protein_probabilistic"
M0804_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0804_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-04+json"
M0804_BASELINE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m08-03+json"
M0804_PARENT: Final = "protein_subtype"
M0804_OWNER: Final = "Bioinformatics"
M0804_SAFETY_CLASS: Final = "S2"
M0804_GATE: Final = "G2"
M0804_PROVISIONAL_ABI: Final = True
M0804_MAX_FEATURES: Final = 512
M0804_MAX_ESTIMATES: Final = M0804_MAX_FEATURES
M0804_MAX_DIAGNOSTICS: Final = 512
M0804_MAX_PRIORS: Final = 128
M0804_MAX_CONSTRAINTS: Final = 128
M0804_MAX_EVIDENCE: Final = 32
M0804_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0804_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0804_EVIDENCE_CLAIM: Final = (
    "Caller-declared M08-03 baseline and probabilistic-estimator evidence; "
    "issuer authority is not authenticated."
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


class ProbabilisticFeatureState(StrEnum):
    """Support state for a caller-declared, already-derived feature."""

    OBSERVED = "observed"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    OOD = "out_of_domain"


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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0804_MAX_EVIDENCE)


class ProbabilisticFeatureObservation(FrozenModel):
    """Strict, lineage-preserving feature values; raw source traversal is prohibited."""

    feature_id: Identifier
    state: ProbabilisticFeatureState
    unit: NonEmptyStr
    value: float | None = None
    isoform_id: Identifier | None = None
    weight: float = Field(gt=0.0, le=1_000.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0804_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_matches_state(self) -> ProbabilisticFeatureObservation:
        if self.state is ProbabilisticFeatureState.OBSERVED and self.value is None:
            raise ValueError("observed probabilistic feature requires a finite value")
        if self.state is not ProbabilisticFeatureState.OBSERVED and self.value is not None:
            raise ValueError("non-observed probabilistic feature cannot carry a value")
        return self


class EstimatorConstraint(FrozenModel):
    constraint_id: Identifier
    expression: NonEmptyStr
    hard: bool
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0804_MAX_EVIDENCE)


class ProbabilisticEstimatorConfiguration(FrozenModel):
    """Locked priors/constraints/optimization declaration; execution is external."""

    configuration_id: Identifier
    version: SemanticVersion
    estimator_family: ProbabilisticEstimatorFamily
    objective: NonEmptyStr
    priors: tuple[ProbabilisticPrior, ...] = Field(
        min_length=1,
        max_length=M0804_MAX_PRIORS,
    )
    constraints: tuple[EstimatorConstraint, ...] = Field(
        default=(),
        max_length=M0804_MAX_CONSTRAINTS,
    )
    optimizer: NonEmptyStr
    seed: int = Field(ge=0)
    max_iterations: int = Field(gt=0, le=10_000_000)
    reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0804_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0804_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0804_MAX_EVIDENCE)

    @model_validator(mode="after")
    def failed_diagnostics_cannot_claim_objective(self) -> OptimizationDiagnostic:
        if self.status in {
            OptimizationDiagnosticStatus.FAILED,
            OptimizationDiagnosticStatus.NOT_EVALUABLE,
        } and (self.objective_value is not None or self.convergence_gap is not None):
            raise ValueError("failed or non-evaluable diagnostics cannot claim optimization values")
        return self


class EstimateTranscriptProteinProbabilisticRequest(FrozenModel):
    """Provisional request for posterior estimation from the M08-03 baseline."""

    operation: Literal["estimate_transcript_protein_probabilistic"] = M0804_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0804_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    baseline_result: ArtifactReference
    configuration: ProbabilisticEstimatorConfiguration
    feature_observations: tuple[ProbabilisticFeatureObservation, ...] = Field(
        default=(),
        max_length=M0804_MAX_FEATURES,
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0804_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateTranscriptProteinProbabilisticRequest:
        if self.baseline_result.media_type != M0804_BASELINE_MEDIA_TYPE:
            raise ValueError("probabilistic request must bind the provisional M08-03 baseline")
        if len({item.feature_id for item in self.feature_observations}) != len(
            self.feature_observations
        ):
            raise ValueError("probabilistic feature ids must be unique")
        if len({item.artifact_id for item in self.source_artifacts}) != len(self.source_artifacts):
            raise ValueError("probabilistic source artifacts must be unique")
        return self


class EstimateTranscriptProteinProbabilisticResult(FrozenModel):
    """Provisional posterior result with diagnostics and explicit abstention."""

    output_type: Literal["transcript_protein_posterior"] = "transcript_protein_posterior"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0804_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateTranscriptProteinProbabilisticRequest
    status: ProbabilisticResultStatus
    estimates: tuple[PosteriorEstimate, ...] = Field(
        default=(),
        max_length=M0804_MAX_ESTIMATES,
    )
    diagnostics: tuple[OptimizationDiagnostic, ...] = Field(
        default=(),
        max_length=M0804_MAX_DIAGNOSTICS,
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M0804_PARENT
    emits_parent: Literal[False] = False
    finding_codes: tuple[Identifier, ...] = Field(default=(), max_length=M0804_MAX_DIAGNOSTICS)
    human_review_required: bool = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0804_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> EstimateTranscriptProteinProbabilisticResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is ProbabilisticResultStatus.ESTIMATED:
            if (
                not self.estimates
                or self.abstention_reason is not None
                or self.human_review_required
                or not any(
                    diagnostic.status is OptimizationDiagnosticStatus.CONVERGED
                    for diagnostic in self.diagnostics
                )
            ):
                raise ValueError("estimated result requires posterior estimates")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("estimated result requires supported status")
        elif (
            self.estimates
            or self.abstention_reason is None
            or not self.human_review_required
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no estimates and safe status")
        if len({item.diagnostic_id for item in self.diagnostics}) != len(self.diagnostics):
            raise ValueError("optimization diagnostic ids must be unique")
        if len({item.feature_id for item in self.estimates}) != len(self.estimates):
            raise ValueError("posterior feature ids must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Return explicit non-estimable uncertainty for safe provisional abstention."""

    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="The provisional M08-04 scaffold has no owner-confirmed calibration.",
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
            "Posterior coverage is not claimed until locked benchmark evidence is available.",
        ),
    )


def expected_provenance(
    request: EstimateTranscriptProteinProbabilisticRequest,
    request_digest: Sha256Digest,
    configuration_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project all seven caller controls into module-local provenance."""

    refs = request.context.references
    decisions = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0804_MODULE_ID,
        module_version=M0804_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(request_digest, request.baseline_result.digest),
        configuration_digest=configuration_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M0804_BASELINE_MEDIA_TYPE",
    "M0804_CONTRACT_VERSION",
    "M0804_EVIDENCE_CLAIM",
    "M0804_GATE",
    "M0804_MAX_CANONICAL_REQUEST_BYTES",
    "M0804_MAX_CANONICAL_RESULT_BYTES",
    "M0804_MAX_CONSTRAINTS",
    "M0804_MAX_DIAGNOSTICS",
    "M0804_MAX_ESTIMATES",
    "M0804_MAX_EVIDENCE",
    "M0804_MAX_FEATURES",
    "M0804_MAX_PRIORS",
    "M0804_MODULE_ID",
    "M0804_OPERATION",
    "M0804_OUTPUT_MEDIA_TYPE",
    "M0804_OWNER",
    "M0804_PARENT",
    "M0804_PROVISIONAL_ABI",
    "M0804_SAFETY_CLASS",
    "EstimateTranscriptProteinProbabilisticRequest",
    "EstimateTranscriptProteinProbabilisticResult",
    "EstimatorConstraint",
    "OptimizationDiagnostic",
    "OptimizationDiagnosticStatus",
    "PosteriorEstimate",
    "PosteriorEstimateKind",
    "ProbabilisticEstimatorConfiguration",
    "ProbabilisticEstimatorFamily",
    "ProbabilisticFeatureObservation",
    "ProbabilisticFeatureState",
    "ProbabilisticPrior",
    "ProbabilisticPriorKind",
    "ProbabilisticResultStatus",
    "expected_provenance",
    "expected_uncertainty",
]
