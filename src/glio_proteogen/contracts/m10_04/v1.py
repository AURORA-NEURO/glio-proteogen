"""Provisional M10-04 probabilistic/advanced estimator contracts.

The dossier freezes primary inference, diagnostics, seeds, and failure
handling, but not the public ABI, posterior representation, baseline handoff,
or model catalogue.  Every symbol below is provisional scaffolding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m10_04.canonical import (
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

M1004_MODULE_ID: Final = "GLIO-PROTEOGEN-M10-04"
M1004_OPERATION: Final = "estimate_protein_rna_discordance_probabilistic"
M1004_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1004_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-04+json"
M1004_BASELINE_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-03+json"
M1004_PARENT: Final = "protein_rna_discordance"
M1004_OWNER: Final = "Quality engineering"
M1004_SAFETY_CLASS: Final = "S2"
M1004_GATE: Final = "G2"
M1004_PROVISIONAL_ABI: Final = True
M1004_MAX_ESTIMATES: Final = 512
M1004_MAX_DIAGNOSTICS: Final = 512
M1004_MAX_PRIORS: Final = 128
M1004_MAX_CONSTRAINTS: Final = 128
M1004_MAX_EVIDENCE: Final = 32
M1004_MIN_DIAGNOSTICS: Final = 1
M1004_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1004_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1004_EVIDENCE_CLAIM: Final = (
    "Caller-declared M10-03 baseline and probabilistic-estimator evidence; "
    "issuer authority is not authenticated."
)


class ProbabilisticEstimatorFamily(StrEnum):
    LEARNED = "probabilistic_learned"
    MECHANISM_GUIDED = "mechanism_guided"
    STRUCTURE_AWARE = "structure_aware_proteoform"


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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1004_MAX_EVIDENCE)

    @model_validator(mode="after")
    def evidence_roles_are_explicit(self) -> ProbabilisticPrior:
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("prior evidence must use the evidence role")
        return self


class EstimatorConstraint(FrozenModel):
    constraint_id: Identifier
    expression: NonEmptyStr
    hard: bool
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1004_MAX_EVIDENCE)

    @model_validator(mode="after")
    def evidence_roles_are_explicit(self) -> EstimatorConstraint:
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("constraint evidence must use the evidence role")
        return self


class ProbabilisticEstimatorConfiguration(FrozenModel):
    """Locked priors, constraints, optimization, and deterministic seed."""

    configuration_id: Identifier
    version: SemanticVersion
    estimator_family: ProbabilisticEstimatorFamily
    objective: NonEmptyStr
    priors: tuple[ProbabilisticPrior, ...] = Field(min_length=1, max_length=M1004_MAX_PRIORS)
    constraints: tuple[EstimatorConstraint, ...] = Field(
        default=(), max_length=M1004_MAX_CONSTRAINTS
    )
    optimizer: NonEmptyStr
    seed: int = Field(ge=0)
    max_iterations: int = Field(gt=0, le=10_000_000)
    reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1004_MAX_EVIDENCE)

    @model_validator(mode="after")
    def configuration_ids_are_unique(self) -> ProbabilisticEstimatorConfiguration:
        if len({item.prior_id for item in self.priors}) != len(self.priors):
            raise ValueError("probabilistic prior ids must be unique")
        if len({item.constraint_id for item in self.constraints}) != len(self.constraints):
            raise ValueError("estimator constraint ids must be unique")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("configuration evidence must use the evidence role")
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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1004_MAX_EVIDENCE)

    @model_validator(mode="after")
    def posterior_shape_is_closed(self) -> PosteriorEstimate:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        if self.kind is PosteriorEstimateKind.SCALAR:
            if self.estimate_value is None or has_interval or self.category is not None:
                raise ValueError("scalar posterior requires one scalar value")
        elif self.kind is PosteriorEstimateKind.INTERVAL:
            if (
                self.estimate_value is None
                or self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or not self.lower_bound <= self.estimate_value <= self.upper_bound
                or self.category is not None
            ):
                raise ValueError("interval posterior requires ordered bounds and center")
        elif self.category is None or self.estimate_value is not None or has_interval:
            raise ValueError("categorical posterior requires only a category")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("posterior evidence must use the evidence role")
        return self


class OptimizationDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: OptimizationDiagnosticStatus
    objective: NonEmptyStr
    iteration_count: int = Field(ge=0)
    objective_value: float | None = None
    convergence_gap: float | None = Field(default=None, ge=0.0)
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1004_MAX_EVIDENCE)

    @model_validator(mode="after")
    def diagnostic_is_finite_and_attributed(self) -> OptimizationDiagnostic:
        if self.status is OptimizationDiagnosticStatus.CONVERGED and (
            self.objective_value is None or self.convergence_gap is None
        ):
            raise ValueError("converged diagnostic requires objective value and convergence gap")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("diagnostic evidence must use the evidence role")
        return self


class EstimateProteinRnaDiscordanceProbabilisticRequest(FrozenModel):
    """Provisional request for posterior estimation from the M10-03 baseline."""

    operation: Literal["estimate_protein_rna_discordance_probabilistic"] = M1004_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1004_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    baseline_result: ArtifactReference
    configuration: ProbabilisticEstimatorConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1004_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateProteinRnaDiscordanceProbabilisticRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request_id must match request_id")
        if self.baseline_result.media_type != M1004_BASELINE_MEDIA_TYPE:
            raise ValueError("probabilistic request must bind the provisional M10-03 baseline")
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("source artifacts must have unique identifiers")
        return self


class ProteinRnaDiscordanceProbabilisticResult(FrozenModel):
    """Provisional posterior result with diagnostics and explicit abstention."""

    output_type: Literal["protein_rna_discordance_posterior"] = "protein_rna_discordance_posterior"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1004_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateProteinRnaDiscordanceProbabilisticRequest
    status: ProbabilisticResultStatus
    estimates: tuple[PosteriorEstimate, ...] = Field(default=(), max_length=M1004_MAX_ESTIMATES)
    diagnostics: tuple[OptimizationDiagnostic, ...] = Field(
        min_length=M1004_MIN_DIAGNOSTICS, max_length=M1004_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1004_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1004_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceProbabilisticResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("every result requires evidence references with the evidence role")
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
        if self.status is ProbabilisticResultStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstention requires human review acknowledgement")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Return explicit non-estimable uncertainty before owner-locked training."""

    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "The provisional M10-04 estimator has no owner-locked training corpus, "
            "posterior calibration, or transport envelope."
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
            "No unsupported or missing evidence is converted into a negative finding.",
        ),
    )


def expected_provenance(
    request: EstimateProteinRnaDiscordanceProbabilisticRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project all seven caller controls and immutable estimator inputs."""

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
        module_id=M1004_MODULE_ID,
        module_version=M1004_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.baseline_result.digest,
            request.configuration.reference.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=request.configuration.reference.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M1004_BASELINE_MEDIA_TYPE",
    "M1004_CONTRACT_VERSION",
    "M1004_EVIDENCE_CLAIM",
    "M1004_GATE",
    "M1004_MAX_CANONICAL_REQUEST_BYTES",
    "M1004_MAX_CANONICAL_RESULT_BYTES",
    "M1004_MAX_CONSTRAINTS",
    "M1004_MAX_DIAGNOSTICS",
    "M1004_MAX_ESTIMATES",
    "M1004_MAX_EVIDENCE",
    "M1004_MAX_PRIORS",
    "M1004_MIN_DIAGNOSTICS",
    "M1004_MODULE_ID",
    "M1004_OPERATION",
    "M1004_OUTPUT_MEDIA_TYPE",
    "M1004_OWNER",
    "M1004_PARENT",
    "M1004_PROVISIONAL_ABI",
    "M1004_SAFETY_CLASS",
    "EstimateProteinRnaDiscordanceProbabilisticRequest",
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
    "ProteinRnaDiscordanceProbabilisticResult",
    "expected_provenance",
    "expected_uncertainty",
]
