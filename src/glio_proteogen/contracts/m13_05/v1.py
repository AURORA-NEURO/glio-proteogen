"""Provisional M13-05 longitudinal/evolutionary model contracts.

The M13-05 dossier specifies a time-indexed trajectory and explicit change-point
object.  Its public ABI is not yet frozen, so this contract is deliberately
marked provisional while preserving the safety boundary: ordered observations,
future-leakage checks, uncertainty, evidence, and safe abstention.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m13_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 4532-4575.
M1305_MODULE_ID: Final = "GLIO-PROTEOGEN-M13-05"
M1305_OPERATION: Final = "infer_proteotype_longitudinal_evolution"
M1305_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1305_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m13-05+json"
M1305_M1304_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m13-04+json"
M1305_PARENT: Final = "proteotype"
M1305_OWNER: Final = "Scientific engineering"
M1305_SAFETY_CLASS: Final = "S2"
M1305_GATE: Final = "G2"
M1305_PROVISIONAL_ABI: Final = True
M1305_MAX_OBSERVATIONS: Final = 256
M1305_MAX_STATES: Final = 256
M1305_MAX_CHANGE_POINTS: Final = 128
M1305_MAX_EVIDENCE: Final = 64
M1305_MAX_DIAGNOSTICS: Final = 64
M1305_MAX_DIMENSIONS: Final = 16
M1305_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1305_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class TrajectoryDimension(StrEnum):
    TIME_COURSE = "time_course"
    PRIMARY_RECURRENCE = "primary_recurrence"
    TREATMENT_ERA = "treatment_era"
    CLONE = "clone"
    TERRITORY = "territory"
    STATE_TRANSITION = "state_transition"


class EvolutionModelFamily(StrEnum):
    BAYESIAN_GRAPH = "bayesian_graph"
    STATE_SPACE = "state_space"
    MECHANISTIC = "mechanistic"
    FOUNDATION_ASSISTED = "foundation_assisted"
    MIXTURE_OF_EXPERTS = "mixture_of_experts"


class TrajectoryStatus(StrEnum):
    MODELED = "modeled"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class ChangePointStatus(StrEnum):
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    NOT_EVALUABLE = "not_evaluable"


class LongitudinalDiagnosticCode(StrEnum):
    FUTURE_LEAKAGE_BLOCKED = "future_leakage_blocked"
    TEMPORAL_ORDERING_VERIFIED = "temporal_ordering_verified"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class TimePointObservation(FrozenModel):
    """One immutable, ordered observation used by the longitudinal model."""

    observation_id: Identifier
    sequence: int = Field(ge=0, le=M1305_MAX_OBSERVATIONS)
    observed_at: AwareDatetime
    territory: NonEmptyStr
    treatment_era: NonEmptyStr
    feature_artifact: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1305_MAX_EVIDENCE)


class EvolutionModelConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: EvolutionModelFamily
    objective: NonEmptyStr
    model_reference: ArtifactReference
    locked: Literal[True] = True
    future_leakage_blocked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1305_MAX_EVIDENCE)


class TrajectoryPolicy(FrozenModel):
    dimensions: tuple[TrajectoryDimension, ...] = Field(
        min_length=1, max_length=M1305_MAX_DIMENSIONS
    )
    minimum_observations: int = Field(ge=2, le=M1305_MAX_OBSERVATIONS)
    ordered_observations_required: Literal[True] = True
    future_leakage_blocked: Literal[True] = True
    configuration: EvolutionModelConfiguration

    @model_validator(mode="after")
    def dimensions_are_unique(self) -> TrajectoryPolicy:
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("trajectory dimensions must be unique")
        return self


class TrajectoryState(FrozenModel):
    state_id: Identifier
    sequence: int = Field(ge=0, le=M1305_MAX_STATES)
    label: NonEmptyStr
    posterior_probability: float = Field(ge=0.0, le=1.0)
    observation_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1305_MAX_OBSERVATIONS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1305_MAX_EVIDENCE)


class ChangePoint(FrozenModel):
    change_point_id: Identifier
    sequence: int = Field(ge=1, le=M1305_MAX_OBSERVATIONS)
    status: ChangePointStatus
    before_state_id: Identifier | None = None
    after_state_id: Identifier | None = None
    posterior_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1305_MAX_EVIDENCE)

    @model_validator(mode="after")
    def detected_shape_is_closed(self) -> ChangePoint:
        if self.status is ChangePointStatus.DETECTED:
            if (
                self.before_state_id is None
                or self.after_state_id is None
                or self.posterior_probability is None
                or not self.evidence
            ):
                raise ValueError("detected change point requires states, posterior, and evidence")
        elif any(
            value is not None
            for value in (self.before_state_id, self.after_state_id, self.posterior_probability)
        ):
            raise ValueError("non-detected change point cannot carry detected fields")
        return self


class LongitudinalDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    code: LongitudinalDiagnosticCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1305_MAX_EVIDENCE)


class ModelProteotypeLongitudinalEvolutionRequest(FrozenModel):
    """Provisional request bound to the M13-04 mechanism/state result."""

    operation: Literal["infer_proteotype_longitudinal_evolution"] = M1305_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1305_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    network_state_result: ArtifactReference
    policy: TrajectoryPolicy
    observations: tuple[TimePointObservation, ...] = Field(
        min_length=2, max_length=M1305_MAX_OBSERVATIONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1305_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_temporally_closed(self) -> ModelProteotypeLongitudinalEvolutionRequest:
        if self.network_state_result.media_type != M1305_M1304_RESULT_MEDIA_TYPE:
            raise ValueError("longitudinal request must bind the provisional M13-04 result")
        ids = tuple(item.observation_id for item in self.observations)
        if len(set(ids)) != len(ids):
            raise ValueError("observation identifiers must be unique")
        sequences = tuple(item.sequence for item in self.observations)
        if sequences != tuple(sorted(sequences)) or len(set(sequences)) != len(sequences):
            raise ValueError("observations must be strictly ordered by sequence")
        times = tuple(item.observed_at for item in self.observations)
        if times != tuple(sorted(times)) or len(set(times)) != len(times):
            raise ValueError("observations must be strictly ordered by observed_at")
        if len(self.observations) < self.policy.minimum_observations:
            raise ValueError("history does not meet the configured minimum")
        return self


class ProteotypeLongitudinalEvolutionResult(FrozenModel):
    """Time-indexed trajectory with explicit change points and safe abstention."""

    output_type: Literal["proteotype_longitudinal_evolution"] = "proteotype_longitudinal_evolution"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1305_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ModelProteotypeLongitudinalEvolutionRequest
    status: TrajectoryStatus
    trajectory: tuple[TrajectoryState, ...] = Field(default=(), max_length=M1305_MAX_STATES)
    change_points: tuple[ChangePoint, ...] = Field(default=(), max_length=M1305_MAX_CHANGE_POINTS)
    diagnostics: tuple[LongitudinalDiagnostic, ...] = Field(
        default=(), max_length=M1305_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1305_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1305_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    temporal_order_verified: Literal[True] = True
    future_leakage_checked: Literal[True] = True
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeLongitudinalEvolutionResult:  # noqa: PLR0912
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("every result requires evidence references with the evidence role")
        state_ids = tuple(state.state_id for state in self.trajectory)
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("trajectory state identifiers must be unique")
        change_ids = tuple(item.change_point_id for item in self.change_points)
        if len(change_ids) != len(set(change_ids)):
            raise ValueError("change-point identifiers must be unique")
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("diagnostic identifiers must be unique")
        if self.status is TrajectoryStatus.MODELED:
            if (
                not self.trajectory
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("modeled result requires a supported trajectory")
        elif (
            self.trajectory
            or self.change_points
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no trajectory and safe status")
        state_sequences = tuple(state.sequence for state in self.trajectory)
        if state_sequences != tuple(sorted(state_sequences)) or len(state_sequences) != len(
            set(state_sequences)
        ):
            raise ValueError("trajectory states must be ordered")
        if len(self.change_points) > len(self.request.observations):
            raise ValueError("change-point count exceeds observation history")
        change_sequences = tuple(item.sequence for item in self.change_points)
        if change_sequences != tuple(sorted(change_sequences)) or len(change_sequences) != len(
            set(change_sequences)
        ):
            raise ValueError("change points must be ordered")
        if any(
            point.status is ChangePointStatus.DETECTED
            and (point.before_state_id not in state_ids or point.after_state_id not in state_ids)
            for point in self.change_points
        ):
            raise ValueError("detected change points must reference trajectory states")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, supported: bool) -> UncertaintyProfile:
    """Construct all seven uncertainty dimensions without hiding abstention."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "The locked trajectory grammar and ordered caller-declared observations are "
            "inside the provisional support domain."
            if supported
            else (
                "Temporal history, upstream support, or model configuration was not safely "
                "evaluable."
            )
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
            "The trajectory is deterministic over caller-declared observations; artifact "
            "contents are opaque and never traversed.",
            "Nominal coverage is provisional and requires locked external calibration evidence.",
        ),
    )


def expected_provenance(
    request: ModelProteotypeLongitudinalEvolutionRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project the seven caller-declared controls into auditable provenance."""

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
        module_id=M1305_MODULE_ID,
        module_version=M1305_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.network_state_result.digest,
            *(observation.feature_artifact.digest for observation in request.observations),
            *(artifact.digest for artifact in request.source_artifacts),
            *(item.evidence_digest for item in decisions),
        ),
        configuration_digest=request.policy.configuration.model_reference.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M1305_CONTRACT_VERSION",
    "M1305_GATE",
    "M1305_M1304_RESULT_MEDIA_TYPE",
    "M1305_MAX_CANONICAL_REQUEST_BYTES",
    "M1305_MAX_CANONICAL_RESULT_BYTES",
    "M1305_MAX_CHANGE_POINTS",
    "M1305_MAX_DIAGNOSTICS",
    "M1305_MAX_DIMENSIONS",
    "M1305_MAX_EVIDENCE",
    "M1305_MAX_OBSERVATIONS",
    "M1305_MAX_STATES",
    "M1305_MODULE_ID",
    "M1305_OPERATION",
    "M1305_OUTPUT_MEDIA_TYPE",
    "M1305_OWNER",
    "M1305_PARENT",
    "M1305_PROVISIONAL_ABI",
    "M1305_SAFETY_CLASS",
    "ChangePoint",
    "ChangePointStatus",
    "EvolutionModelConfiguration",
    "EvolutionModelFamily",
    "LongitudinalDiagnostic",
    "LongitudinalDiagnosticCode",
    "ModelProteotypeLongitudinalEvolutionRequest",
    "ProteotypeLongitudinalEvolutionResult",
    "TimePointObservation",
    "TrajectoryDimension",
    "TrajectoryPolicy",
    "TrajectoryState",
    "TrajectoryStatus",
    "expected_provenance",
    "expected_uncertainty",
]
