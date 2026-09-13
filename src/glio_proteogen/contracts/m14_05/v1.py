"""Provisional M14-05 longitudinal and evolutionary model contracts.

The dossier requires a time-indexed trajectory and explicit change-point object
under Microenvironment protein deconvolution.  The ABI is not frozen; this
contract preserves ordering, leakage prevention, uncertainty, evidence, and
safe abstention for the protein-subtype parent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m14_05.canonical import (
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

# PROVISIONAL ABI: behavior bound to the authoritative dossier slice below.
M1405_MODULE_ID: Final = "GLIO-PROTEOGEN-M14-05"
M1405_DOSSIER_SLICE: Final = "4892-4932"
M1405_REQUIREMENT_SHA256: Final = (
    "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M1405_OPERATION: Final = "infer_protein_subtype_longitudinal_evolution"
M1405_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1405_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-05+json"
M1405_M1404_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-04+json"
M1405_PARENT: Final = "protein_subtype"
M1405_OWNER: Final = "Computational biology"
M1405_SAFETY_CLASS: Final = "S2"
M1405_GATE: Final = "G2"
M1405_PROVISIONAL_ABI: Final = True
M1405_EVIDENCE_CLAIM: Final = (
    "Caller-declared ordered observations and M14-05 metadata replay; "
    "issuer authority and biological state are not authenticated."
)
M1405_MAX_OBSERVATIONS: Final = 256
M1405_MAX_STATES: Final = 256
M1405_MAX_CHANGE_POINTS: Final = 128
M1405_MAX_EVIDENCE: Final = 64
M1405_MAX_DIAGNOSTICS: Final = 64
M1405_MAX_DIMENSIONS: Final = 16
M1405_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1405_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1405_MAX_EFFECT: Final = 20.0
M1405_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M1405_MAX_BOOTSTRAP_REPLICATES: Final = 256


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
    OPEN_SET_PROTEOTYPE = "open_set_proteotype"


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


class LongitudinalEvidenceState(StrEnum):
    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class GliomaTrajectoryProgram(StrEnum):
    RTK_PI3K_AKT_MTOR = "RTK_PI3K_AKT_MTOR"
    P53_CELL_CYCLE = "P53_CELL_CYCLE"
    IDH_HIF1A = "IDH_HIF1A"
    MESENCHYMAL_PROGRAM = "MESENCHYMAL_PROGRAM"
    PROLIFERATION = "PROLIFERATION"


class TimePointObservation(FrozenModel):
    """One immutable, ordered observation used by the evolution model."""

    observation_id: Identifier
    sequence: int = Field(ge=0, le=M1405_MAX_OBSERVATIONS)
    observed_at: AwareDatetime
    territory: NonEmptyStr
    treatment_era: NonEmptyStr
    feature_artifact: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1405_MAX_EVIDENCE)
    program: GliomaTrajectoryProgram | None = None
    evidence_state: LongitudinalEvidenceState | None = None
    standardized_effect: float | None = Field(
        default=None, ge=-M1405_MAX_EFFECT, le=M1405_MAX_EFFECT, allow_inf_nan=False
    )
    standard_error: float | None = Field(
        default=None, gt=0.0, le=M1405_MAX_EFFECT, allow_inf_nan=False
    )
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def typed_measurement_shape_is_closed(self) -> TimePointObservation:
        typed = self.evidence_state is not None or self.standardized_effect is not None
        if not typed:
            if self.standard_error is not None or self.program is not None:
                raise ValueError("typed temporal measurements require an effect and evidence state")
            return self
        if self.evidence_state is None:
            raise ValueError("typed temporal effects require evidence_state")
        active = self.evidence_state in {
            LongitudinalEvidenceState.OBSERVED,
            LongitudinalEvidenceState.LEFT_CENSORED,
        }
        if active:
            if (
                self.standardized_effect is None
                or self.standard_error is None
                or self.program is None
            ):
                raise ValueError(
                    "observed temporal evidence requires program, effect, and standard error"
                )
            if self.quality_weight <= 0.0:
                raise ValueError("active temporal evidence requires positive quality weight")
        elif (
            self.standardized_effect is not None
            or self.standard_error is not None
            or self.quality_weight != 0.0
        ):
            raise ValueError("missing or unsupported temporal evidence cannot carry a value")
        return self


class EvolutionModelConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: EvolutionModelFamily
    objective: NonEmptyStr
    model_reference: ArtifactReference
    locked: Literal[True] = True
    future_leakage_blocked: Literal[True] = True
    bootstrap_replicates: int = Field(
        default=M1405_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M1405_MAX_BOOTSTRAP_REPLICATES,
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1405_MAX_EVIDENCE)


class TrajectoryPolicy(FrozenModel):
    dimensions: tuple[TrajectoryDimension, ...] = Field(
        min_length=1, max_length=M1405_MAX_DIMENSIONS
    )
    minimum_observations: int = Field(ge=2, le=M1405_MAX_OBSERVATIONS)
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
    sequence: int = Field(ge=0, le=M1405_MAX_STATES)
    label: NonEmptyStr
    posterior_probability: float = Field(ge=0.0, le=1.0)
    observation_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1405_MAX_OBSERVATIONS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1405_MAX_EVIDENCE)
    standardized_state: float | None = Field(
        default=None, ge=-M1405_MAX_EFFECT, le=M1405_MAX_EFFECT, allow_inf_nan=False
    )
    lower_bound: float | None = Field(
        default=None, ge=-M1405_MAX_EFFECT, le=M1405_MAX_EFFECT, allow_inf_nan=False
    )
    upper_bound: float | None = Field(
        default=None, ge=-M1405_MAX_EFFECT, le=M1405_MAX_EFFECT, allow_inf_nan=False
    )
    evidence_count: int = Field(default=0, ge=0, le=M1405_MAX_OBSERVATIONS)
    stability: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    top_drivers: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def typed_state_interval_is_closed(self) -> TrajectoryState:
        if any(value is not None for value in (self.lower_bound, self.upper_bound)):
            if (
                self.standardized_state is None
                or self.lower_bound is None
                or self.upper_bound is None
            ):
                raise ValueError("typed trajectory state requires a complete state interval")
            if self.lower_bound > self.upper_bound:
                raise ValueError("trajectory state interval must be ordered")
        return self


class ChangePoint(FrozenModel):
    change_point_id: Identifier
    sequence: int = Field(ge=1, le=M1405_MAX_OBSERVATIONS)
    status: ChangePointStatus
    before_state_id: Identifier | None = None
    after_state_id: Identifier | None = None
    posterior_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1405_MAX_EVIDENCE)
    effect_delta: float | None = Field(
        default=None, ge=-M1405_MAX_EFFECT, le=M1405_MAX_EFFECT, allow_inf_nan=False
    )
    lower_bound: float | None = Field(
        default=None, ge=-M1405_MAX_EFFECT, le=M1405_MAX_EFFECT, allow_inf_nan=False
    )
    upper_bound: float | None = Field(
        default=None, ge=-M1405_MAX_EFFECT, le=M1405_MAX_EFFECT, allow_inf_nan=False
    )

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1405_MAX_EVIDENCE)
    solver_iterations: int | None = Field(default=None, ge=0, le=1000)
    solver_objective: float | None = Field(default=None, ge=0.0, le=1e9, allow_inf_nan=False)
    solver_max_update: float | None = Field(
        default=None, ge=0.0, le=M1405_MAX_EFFECT, allow_inf_nan=False
    )
    objective_trace_digest: Sha256Digest | None = None


class ModelProteinSubtypeLongitudinalEvolutionRequest(FrozenModel):
    """Provisional request bound to the M14-04 mechanism/state result."""

    operation: Literal["infer_protein_subtype_longitudinal_evolution"] = M1405_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1405_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    network_state_result: ArtifactReference
    policy: TrajectoryPolicy
    observations: tuple[TimePointObservation, ...] = Field(
        min_length=2, max_length=M1405_MAX_OBSERVATIONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1405_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_temporally_closed(self) -> ModelProteinSubtypeLongitudinalEvolutionRequest:
        if self.network_state_result.media_type != M1405_M1404_RESULT_MEDIA_TYPE:
            raise ValueError("longitudinal request must bind the provisional M14-04 result")
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


class ProteinSubtypeLongitudinalEvolutionResult(FrozenModel):
    """Time-indexed protein-subtype trajectory with explicit change points."""

    output_type: Literal["protein_subtype_longitudinal_evolution"] = (
        "protein_subtype_longitudinal_evolution"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1405_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ModelProteinSubtypeLongitudinalEvolutionRequest
    status: TrajectoryStatus
    trajectory: tuple[TrajectoryState, ...] = Field(default=(), max_length=M1405_MAX_STATES)
    change_points: tuple[ChangePoint, ...] = Field(default=(), max_length=M1405_MAX_CHANGE_POINTS)
    diagnostics: tuple[LongitudinalDiagnostic, ...] = Field(
        default=(), max_length=M1405_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M1405_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1405_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    temporal_order_verified: Literal[True] = True
    future_leakage_checked: Literal[True] = True
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeLongitudinalEvolutionResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is TrajectoryStatus.MODELED:
            if (
                not self.trajectory
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
            ):
                raise ValueError("modeled result requires a review-only trajectory")
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
    "M1405_CONTRACT_VERSION",
    "M1405_DEFAULT_BOOTSTRAP_REPLICATES",
    "M1405_DOSSIER_SLICE",
    "M1405_EVIDENCE_CLAIM",
    "M1405_GATE",
    "M1405_M1404_RESULT_MEDIA_TYPE",
    "M1405_MAX_BOOTSTRAP_REPLICATES",
    "M1405_MAX_CANONICAL_REQUEST_BYTES",
    "M1405_MAX_CANONICAL_RESULT_BYTES",
    "M1405_MAX_CHANGE_POINTS",
    "M1405_MAX_DIAGNOSTICS",
    "M1405_MAX_DIMENSIONS",
    "M1405_MAX_EFFECT",
    "M1405_MAX_EVIDENCE",
    "M1405_MAX_OBSERVATIONS",
    "M1405_MAX_STATES",
    "M1405_MODULE_ID",
    "M1405_OPERATION",
    "M1405_OUTPUT_MEDIA_TYPE",
    "M1405_OWNER",
    "M1405_PARENT",
    "M1405_PROVISIONAL_ABI",
    "M1405_REQUIREMENT_SHA256",
    "M1405_SAFETY_CLASS",
    "ChangePoint",
    "ChangePointStatus",
    "EvolutionModelConfiguration",
    "EvolutionModelFamily",
    "GliomaTrajectoryProgram",
    "LongitudinalDiagnostic",
    "LongitudinalDiagnosticCode",
    "LongitudinalEvidenceState",
    "ModelProteinSubtypeLongitudinalEvolutionRequest",
    "ProteinSubtypeLongitudinalEvolutionResult",
    "TimePointObservation",
    "TrajectoryDimension",
    "TrajectoryPolicy",
    "TrajectoryState",
    "TrajectoryStatus",
]
