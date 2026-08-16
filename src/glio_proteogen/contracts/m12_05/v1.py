"""Provisional M12-05 longitudinal/evolutionary model contracts.

The M12-05 dossier specifies a time-indexed trajectory and explicit change-point
object.  Its public ABI is not yet frozen, so this contract is deliberately
marked provisional while preserving the safety boundary: ordered observations,
future-leakage checks, uncertainty, evidence, and safe abstention.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m12_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 4172-4212.
M1205_MODULE_ID: Final = "GLIO-PROTEOGEN-M12-05"
M1205_OPERATION: Final = "infer_biomarker_panel_longitudinal_evolution"
M1205_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1205_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m12-05+json"
M1205_M1204_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m12-04+json"
M1205_PARENT: Final = "biomarker_panel"
M1205_OWNER: Final = "Platform engineering"
M1205_SAFETY_CLASS: Final = "S2"
M1205_GATE: Final = "G2"
M1205_PROVISIONAL_ABI: Final = True
M1205_MAX_OBSERVATIONS: Final = 256
M1205_MAX_STATES: Final = 256
M1205_MAX_CHANGE_POINTS: Final = 128
M1205_MAX_EVIDENCE: Final = 64
M1205_MAX_DIAGNOSTICS: Final = 64
M1205_MAX_DIMENSIONS: Final = 16
M1205_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1205_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


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
    sequence: int = Field(ge=0, le=M1205_MAX_OBSERVATIONS)
    observed_at: AwareDatetime
    territory: NonEmptyStr
    treatment_era: NonEmptyStr
    feature_artifact: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1205_MAX_EVIDENCE)


class EvolutionModelConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: EvolutionModelFamily
    objective: NonEmptyStr
    model_reference: ArtifactReference
    locked: Literal[True] = True
    future_leakage_blocked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1205_MAX_EVIDENCE)


class TrajectoryPolicy(FrozenModel):
    dimensions: tuple[TrajectoryDimension, ...] = Field(
        min_length=1, max_length=M1205_MAX_DIMENSIONS
    )
    minimum_observations: int = Field(ge=2, le=M1205_MAX_OBSERVATIONS)
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
    sequence: int = Field(ge=0, le=M1205_MAX_STATES)
    label: NonEmptyStr
    posterior_probability: float = Field(ge=0.0, le=1.0)
    observation_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1205_MAX_OBSERVATIONS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1205_MAX_EVIDENCE)


class ChangePoint(FrozenModel):
    change_point_id: Identifier
    sequence: int = Field(ge=1, le=M1205_MAX_OBSERVATIONS)
    status: ChangePointStatus
    before_state_id: Identifier | None = None
    after_state_id: Identifier | None = None
    posterior_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1205_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1205_MAX_EVIDENCE)


class ModelBiomarkerPanelLongitudinalEvolutionRequest(FrozenModel):
    """Provisional request bound to the M12-04 mechanism/state result."""

    operation: Literal["infer_biomarker_panel_longitudinal_evolution"] = M1205_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1205_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    network_state_result: ArtifactReference
    policy: TrajectoryPolicy
    observations: tuple[TimePointObservation, ...] = Field(
        min_length=2, max_length=M1205_MAX_OBSERVATIONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1205_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_temporally_closed(self) -> ModelBiomarkerPanelLongitudinalEvolutionRequest:
        if self.network_state_result.media_type != M1205_M1204_RESULT_MEDIA_TYPE:
            raise ValueError("longitudinal request must bind the provisional M12-04 result")
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


class BiomarkerPanelLongitudinalEvolutionResult(FrozenModel):
    """Time-indexed trajectory with explicit change points and safe abstention."""

    output_type: Literal["biomarker_panel_longitudinal_evolution"] = (
        "biomarker_panel_longitudinal_evolution"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1205_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ModelBiomarkerPanelLongitudinalEvolutionRequest
    status: TrajectoryStatus
    trajectory: tuple[TrajectoryState, ...] = Field(default=(), max_length=M1205_MAX_STATES)
    change_points: tuple[ChangePoint, ...] = Field(default=(), max_length=M1205_MAX_CHANGE_POINTS)
    diagnostics: tuple[LongitudinalDiagnostic, ...] = Field(
        default=(), max_length=M1205_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker_panel"] = M1205_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1205_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    temporal_order_verified: Literal[True] = True
    future_leakage_checked: Literal[True] = True
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelLongitudinalEvolutionResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
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
        if state_sequences != tuple(sorted(state_sequences)):
            raise ValueError("trajectory states must be ordered")
        if len(self.change_points) > len(self.request.observations):
            raise ValueError("change-point count exceeds observation history")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1205_CONTRACT_VERSION",
    "M1205_GATE",
    "M1205_M1204_RESULT_MEDIA_TYPE",
    "M1205_MAX_CANONICAL_REQUEST_BYTES",
    "M1205_MAX_CANONICAL_RESULT_BYTES",
    "M1205_MAX_CHANGE_POINTS",
    "M1205_MAX_DIAGNOSTICS",
    "M1205_MAX_DIMENSIONS",
    "M1205_MAX_EVIDENCE",
    "M1205_MAX_OBSERVATIONS",
    "M1205_MAX_STATES",
    "M1205_MODULE_ID",
    "M1205_OPERATION",
    "M1205_OUTPUT_MEDIA_TYPE",
    "M1205_OWNER",
    "M1205_PARENT",
    "M1205_PROVISIONAL_ABI",
    "M1205_SAFETY_CLASS",
    "BiomarkerPanelLongitudinalEvolutionResult",
    "ChangePoint",
    "ChangePointStatus",
    "EvolutionModelConfiguration",
    "EvolutionModelFamily",
    "LongitudinalDiagnostic",
    "LongitudinalDiagnosticCode",
    "ModelBiomarkerPanelLongitudinalEvolutionRequest",
    "TimePointObservation",
    "TrajectoryDimension",
    "TrajectoryPolicy",
    "TrajectoryState",
    "TrajectoryStatus",
]
