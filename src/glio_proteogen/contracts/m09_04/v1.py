"""Provisional M09-04 probabilistic/advanced estimator contracts.

The dossier freezes primary inference, diagnostics, seeds, and failure
handling, but not the public ABI, posterior representation, M09-03 handoff, or
model catalogue.  All symbols below are provisional scaffolding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m09_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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

M0904_MODULE_ID: Final = "GLIO-PROTEOGEN-M09-04"
M0904_OPERATION: Final = "estimate_complex_activity_probabilistic"
M0904_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0904_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-04+json"
M0904_BASELINE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-03+json"
M0904_PARENT: Final = "complex_activity"
M0904_OWNER: Final = "ML engineering"
M0904_SAFETY_CLASS: Final = "S2"
M0904_GATE: Final = "G2"
M0904_PROVISIONAL_ABI: Final = True
M0904_MAX_ESTIMATES: Final = 512
M0904_MAX_DIAGNOSTICS: Final = 512
M0904_MAX_PRIORS: Final = 128
M0904_MAX_CONSTRAINTS: Final = 128
M0904_MAX_EVIDENCE: Final = 32
M0904_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0904_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0904_EVIDENCE_CLAIM: Final = (
    "Caller-declared M09-03 baseline and probabilistic-estimator evidence; "
    "issuer authority is not authenticated."
)
M0904_MAX_TYPED_OBSERVATIONS: Final = 256
M0904_MAX_TYPED_EFFECT: Final = 8.0
M0904_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M0904_MAX_BOOTSTRAP_REPLICATES: Final = 256
M0904_GLIOMA_MODEL_FAMILY: Final = "glioma-complex-stoichiometric-irls/1.0.0"

# Posterior and optimisation values are part of the signed replay surface.
# Reject non-finite values at the contract boundary instead of normalising them
# after a result has already been produced.
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


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


class ProbabilisticReplayReason(StrEnum):
    VERIFIED = "verified"
    INVALID_RESULT = "invalid_result"
    DIGEST_MISMATCH = "digest_mismatch"
    NON_CANONICAL = "non_canonical"
    OVERSIZED = "oversized"


class ProbabilisticResultStatus(StrEnum):
    ESTIMATED = "estimated"
    ABSTAINED = "abstained"


class ComplexEvidenceState(StrEnum):
    """How one member-level measurement contributes to a typed complex fit."""

    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class ComplexMemberRole(StrEnum):
    """Stoichiometric role of a protein inside the declared complex."""

    ESSENTIAL = "essential"
    SUPPORTING = "supporting"


class GliomaComplexProgram(StrEnum):
    """Glioma-relevant complexes grouped by a reviewable biological program."""

    RTK_PI3K_AKT_MTOR = "RTK_PI3K_AKT_MTOR"
    P53_DNA_REPAIR = "P53_DNA_REPAIR"
    CHROMATIN_REMODELING = "CHROMATIN_REMODELING"
    HYPOXIA_ANGIOGENESIS = "HYPOXIA_ANGIOGENESIS"
    CELL_CYCLE = "CELL_CYCLE"


class ProbabilisticPrior(FrozenModel):
    prior_id: Identifier
    version: SemanticVersion
    kind: ProbabilisticPriorKind
    parameters: tuple[float, ...] = Field(min_length=1, max_length=32)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0904_MAX_EVIDENCE)


class EstimatorConstraint(FrozenModel):
    constraint_id: Identifier
    expression: NonEmptyStr
    hard: bool
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0904_MAX_EVIDENCE)


class ComplexMemberObservation(FrozenModel):
    """Explicit member-level evidence for the typed glioma complex lane.

    The compatibility ABI only carries artifact references.  This additive
    observation makes the scientific path operate on actual standardized
    effects, standard errors, member roles, and stoichiometric weights while
    preserving missing and unsupported states as non-observations.
    """

    observation_id: Identifier
    complex_id: Identifier
    member_id: Identifier
    program: GliomaComplexProgram | None = None
    member_role: ComplexMemberRole = ComplexMemberRole.SUPPORTING
    evidence_state: ComplexEvidenceState | None = None
    standardized_effect: float | None = Field(
        default=None, ge=-M0904_MAX_TYPED_EFFECT, le=M0904_MAX_TYPED_EFFECT
    )
    standard_error: float | None = Field(default=None, gt=0.0, le=M0904_MAX_TYPED_EFFECT)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    stoichiometric_weight: float = Field(default=1.0, gt=0.0, le=16.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0904_MAX_EVIDENCE)

    @model_validator(mode="after")
    def typed_observation_shape_is_closed(self) -> ComplexMemberObservation:
        typed = self.evidence_state is not None or self.standardized_effect is not None
        if not typed:
            if self.standard_error is not None or self.program is not None:
                raise ValueError("typed complex measurements require an effect and evidence state")
            return self
        if self.evidence_state is None:
            raise ValueError("typed complex effects require evidence_state")
        active = self.evidence_state in {
            ComplexEvidenceState.OBSERVED,
            ComplexEvidenceState.LEFT_CENSORED,
        }
        if active:
            if (
                self.standardized_effect is None
                or self.standard_error is None
                or self.program is None
            ):
                raise ValueError(
                    "active complex evidence requires program, effect, and standard error"
                )
            if self.quality_weight <= 0.0:
                raise ValueError("active complex evidence requires positive quality weight")
        elif (
            self.standardized_effect is not None
            or self.standard_error is not None
            or self.quality_weight != 0.0
        ):
            raise ValueError("missing or unsupported complex evidence cannot carry a value")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("complex member evidence must use the evidence role")
        return self


class ProbabilisticEstimatorConfiguration(FrozenModel):
    """Locked priors/constraints/optimization declaration; execution is external."""

    configuration_id: Identifier
    version: SemanticVersion
    estimator_family: ProbabilisticEstimatorFamily
    objective: NonEmptyStr
    priors: tuple[ProbabilisticPrior, ...] = Field(min_length=1, max_length=M0904_MAX_PRIORS)
    constraints: tuple[EstimatorConstraint, ...] = Field(
        default=(), max_length=M0904_MAX_CONSTRAINTS
    )
    optimizer: NonEmptyStr
    seed: int = Field(ge=0)
    max_iterations: int = Field(gt=0, le=10_000_000)
    bootstrap_replicates: int = Field(
        default=M0904_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M0904_MAX_BOOTSTRAP_REPLICATES,
    )
    reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0904_MAX_EVIDENCE)

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
    estimate_value: FiniteFloat | None = None
    lower_bound: FiniteFloat | None = None
    upper_bound: FiniteFloat | None = None
    category: NonEmptyStr | None = None
    posterior_mass: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)
    evidence_count: int = Field(default=0, ge=0, le=M0904_MAX_TYPED_OBSERVATIONS)
    stability: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)
    discordance: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)
    top_drivers: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    ablation_effects: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0904_MAX_EVIDENCE)

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
    objective_value: FiniteFloat | None = None
    convergence_gap: FiniteFloat | None = Field(default=None, ge=0.0)
    message: NonEmptyStr
    model_family: NonEmptyStr | None = None
    objective_trace_digest: Sha256Digest | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0904_MAX_EVIDENCE)

    @model_validator(mode="after")
    def diagnostic_shape_is_closed(self) -> OptimizationDiagnostic:
        if self.status is OptimizationDiagnosticStatus.CONVERGED:
            if self.objective_value is None or self.convergence_gap is None:
                raise ValueError("converged diagnostic requires objective and convergence gap")
        elif self.objective_value is not None and self.convergence_gap is None:
            raise ValueError("objective value requires a convergence gap")
        return self


class EstimateComplexActivityProbabilisticVerification(FrozenModel):
    """Content and deterministic replay status for a published result."""

    content_verified: bool
    deterministic_verified: bool
    verified: bool
    result_digest: Sha256Digest | None = None
    reason: ProbabilisticReplayReason

    @model_validator(mode="after")
    def verification_flags_are_closed(
        self,
    ) -> EstimateComplexActivityProbabilisticVerification:
        expected = self.content_verified and self.deterministic_verified
        if self.verified != expected:
            raise ValueError("verified must equal content and deterministic verification")
        if self.verified != (self.result_digest is not None):
            raise ValueError("verified results must carry a result digest only")
        return self


class EstimateComplexActivityProbabilisticRequest(FrozenModel):
    """Provisional request for posterior estimation from the M09-03 baseline."""

    operation: Literal["estimate_complex_activity_probabilistic"] = M0904_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0904_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    baseline_result: ArtifactReference
    configuration: ProbabilisticEstimatorConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0904_MAX_EVIDENCE
    )
    typed_observations: tuple[ComplexMemberObservation, ...] = Field(
        default=(), max_length=M0904_MAX_TYPED_OBSERVATIONS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateComplexActivityProbabilisticRequest:
        if self.baseline_result.media_type != M0904_BASELINE_MEDIA_TYPE:
            raise ValueError("probabilistic request must bind the provisional M09-03 baseline")
        if self.typed_observations:
            observation_ids = tuple(item.observation_id for item in self.typed_observations)
            if len(observation_ids) != len(set(observation_ids)):
                raise ValueError("typed complex observation identifiers must be unique")
            member_keys = tuple(
                (item.complex_id, item.member_id) for item in self.typed_observations
            )
            if len(member_keys) != len(set(member_keys)):
                raise ValueError("typed complex member identifiers must be unique per complex")
        return self


class EstimateComplexActivityProbabilisticResult(FrozenModel):
    """Provisional posterior result with diagnostics and explicit abstention."""

    output_type: Literal["complex_activity_posterior"] = "complex_activity_posterior"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0904_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateComplexActivityProbabilisticRequest
    status: ProbabilisticResultStatus
    estimates: tuple[PosteriorEstimate, ...] = Field(default=(), max_length=M0904_MAX_ESTIMATES)
    diagnostics: tuple[OptimizationDiagnostic, ...] = Field(
        default=(), max_length=M0904_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M0904_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0904_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def result_is_closed(self) -> EstimateComplexActivityProbabilisticResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.provenance != expected_provenance(
            self.request,
            self.request_digest,
            sha256_digest(self.request.configuration),
        ):
            raise ValueError("result provenance does not bind the exact request controls")
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("optimization diagnostic ids must be unique")
        if self.status is ProbabilisticResultStatus.ESTIMATED:
            if not self.estimates or self.abstention_reason is not None:
                raise ValueError("estimated result requires posterior estimates")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("estimated result requires supported status")
            if not any(
                item.status is OptimizationDiagnosticStatus.CONVERGED for item in self.diagnostics
            ):
                raise ValueError("estimated result requires a converged diagnostic")
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


def expected_uncertainty(*, typed: bool = False) -> UncertaintyProfile:
    """Return explicit non-estimable uncertainty for safe provisional abstention."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if typed else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if typed else None,
        rationale=(
            "Typed glioma complex member effects were fitted with robust stoichiometric IRLS "
            "and deterministic bootstrap perturbations."
            if typed
            else "The provisional M09-04 scaffold has no owner-confirmed calibration."
        ),
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
            (
                "Bootstrap intervals are deterministic research diagnostics; calibrated clinical "
                "coverage is not claimed."
                if typed
                else (
                    "Posterior coverage is not claimed until locked benchmark evidence is "
                    "available."
                )
            ),
        ),
    )


def expected_provenance(
    request: EstimateComplexActivityProbabilisticRequest,
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
        module_id=M0904_MODULE_ID,
        module_version=M0904_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_digest,
                    request.baseline_result.digest,
                    *(item.digest for item in request.source_artifacts),
                    *(
                        evidence.reference.digest
                        for observation in request.typed_observations
                        for evidence in observation.evidence
                    ),
                }
            )
        ),
        configuration_digest=configuration_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M0904_BASELINE_MEDIA_TYPE",
    "M0904_CONTRACT_VERSION",
    "M0904_DEFAULT_BOOTSTRAP_REPLICATES",
    "M0904_EVIDENCE_CLAIM",
    "M0904_GATE",
    "M0904_GLIOMA_MODEL_FAMILY",
    "M0904_MAX_BOOTSTRAP_REPLICATES",
    "M0904_MAX_CANONICAL_REQUEST_BYTES",
    "M0904_MAX_CANONICAL_RESULT_BYTES",
    "M0904_MAX_CONSTRAINTS",
    "M0904_MAX_DIAGNOSTICS",
    "M0904_MAX_ESTIMATES",
    "M0904_MAX_EVIDENCE",
    "M0904_MAX_PRIORS",
    "M0904_MAX_TYPED_EFFECT",
    "M0904_MAX_TYPED_OBSERVATIONS",
    "M0904_MODULE_ID",
    "M0904_OPERATION",
    "M0904_OUTPUT_MEDIA_TYPE",
    "M0904_OWNER",
    "M0904_PARENT",
    "M0904_PROVISIONAL_ABI",
    "M0904_SAFETY_CLASS",
    "ComplexEvidenceState",
    "ComplexMemberObservation",
    "ComplexMemberRole",
    "EstimateComplexActivityProbabilisticRequest",
    "EstimateComplexActivityProbabilisticResult",
    "EstimateComplexActivityProbabilisticVerification",
    "EstimatorConstraint",
    "FiniteFloat",
    "GliomaComplexProgram",
    "OptimizationDiagnostic",
    "OptimizationDiagnosticStatus",
    "PosteriorEstimate",
    "PosteriorEstimateKind",
    "ProbabilisticEstimatorConfiguration",
    "ProbabilisticEstimatorFamily",
    "ProbabilisticPrior",
    "ProbabilisticPriorKind",
    "ProbabilisticReplayReason",
    "ProbabilisticResultStatus",
    "expected_provenance",
    "expected_uncertainty",
]
