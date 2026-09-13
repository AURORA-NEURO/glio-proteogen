"""Provisional M12-06 perturbation and sensitivity simulator contracts.

The M12-06 dossier defines bounded perturbation responses and a sensitivity
surface.  The public ABI is not frozen, so these types remain provisional while
making assumptions, bounds, negative controls, provenance, and safe abstention
explicit.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m12_06.canonical import (
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

_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + "0" * 64

# PROVISIONAL ABI: inferred solely from dossier lines 4216-4259.
M1206_MODULE_ID: Final = "GLIO-PROTEOGEN-M12-06"
M1206_OPERATION: Final = "simulate_biomarker_panel_perturbation_sensitivity"
M1206_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1206_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m12-06+json"
M1206_PARENT: Final = "biomarker_panel"
M1206_OWNER: Final = "Scientific engineering"
M1206_SAFETY_CLASS: Final = "S2"
M1206_GATE: Final = "G2"
M1206_PROVISIONAL_ABI: Final = True
M1206_MAX_SCENARIOS: Final = 256
M1206_MAX_RESPONSES: Final = 512
M1206_MAX_AXES: Final = 32
M1206_MAX_EVIDENCE: Final = 64
M1206_MAX_FINDINGS: Final = 64
M1206_MAX_ASSUMPTIONS: Final = 64
M1206_MAX_REPLICATES: Final = 64
M1206_MINIMUM_REPLICATES_PER_ARM: Final = 3
M1206_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M1206_MAX_BOOTSTRAP_REPLICATES: Final = 256
M1206_GLIOMA_MODEL_FAMILY: Final = "glioma-panel-perturbation-response-graph/1.0.0"
M1206_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1206_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
_DELTA_TOLERANCE: Final = 1e-9
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class PerturbationKind(StrEnum):
    IN_SILICO = "in_silico"
    PARAMETER_SWEEP = "parameter_sweep"
    ALTERNATIVE_PRIOR = "alternative_prior"
    ASSAY_PERTURBATION = "assay_perturbation"
    MECHANISM_STRESS_TEST = "mechanism_stress_test"


class PerturbationStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    ABSTAINED = "abstained"


class PerturbationResponseStatus(StrEnum):
    EVALUATED = "evaluated"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class SensitivityMetric(StrEnum):
    ABSOLUTE_DELTA = "absolute_delta"
    RELATIVE_DELTA = "relative_delta"
    RANK_CHANGE = "rank_change"
    PROBABILITY_DELTA = "probability_delta"


class SimulatorStatus(StrEnum):
    SIMULATED = "simulated"
    ABSTAINED = "abstained"


class PerturbationFindingCode(StrEnum):
    OUTSIDE_SUPPORT_ENVELOPE = "outside_support_envelope"
    NEGATIVE_CONTROL_FAILED = "negative_control_failed"
    ASSUMPTION_REQUIRED = "assumption_required"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"
    TYPED_INPUT_INCOMPLETE = "typed_input_incomplete"


class SimulatorConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    units_reference: ArtifactReference
    locked: Literal[True] = True
    negative_controls_required: Literal[True] = True
    bounded_responses_required: Literal[True] = True
    model_family: NonEmptyStr | None = None
    bootstrap_replicates: int = Field(
        default=M1206_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M1206_MAX_BOOTSTRAP_REPLICATES,
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1206_MAX_EVIDENCE)


class PerturbationPolicy(FrozenModel):
    maximum_scenarios: int = Field(ge=1, le=M1206_MAX_SCENARIOS)
    response_lower_bound: FiniteFloat
    response_upper_bound: FiniteFloat
    unsupported_abstains: Literal[True] = True
    assumptions_required: Literal[True] = True
    configuration: SimulatorConfiguration

    @model_validator(mode="after")
    def bounds_are_ordered(self) -> PerturbationPolicy:
        if self.response_lower_bound >= self.response_upper_bound:
            raise ValueError("response lower bound must be below upper bound")
        return self


class PerturbationScenario(FrozenModel):
    scenario_id: Identifier
    kind: PerturbationKind
    parameter: NonEmptyStr
    baseline_value: FiniteFloat
    perturbed_value: FiniteFloat
    unit: NonEmptyStr
    status: PerturbationStatus
    assumption: NonEmptyStr
    source_artifact: ArtifactReference
    baseline_measurements: tuple[FiniteFloat, ...] = Field(
        default=(), max_length=M1206_MAX_REPLICATES
    )
    perturbed_measurements: tuple[FiniteFloat, ...] = Field(
        default=(), max_length=M1206_MAX_REPLICATES
    )
    quality_weight: FiniteFloat = Field(default=1.0, ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1206_MAX_EVIDENCE)

    @model_validator(mode="after")
    def unsupported_scenario_is_explicit(self) -> PerturbationScenario:
        if bool(self.baseline_measurements) != bool(self.perturbed_measurements):
            raise ValueError("baseline and perturbed measurements must be supplied together")
        if self.baseline_measurements and (
            len(self.baseline_measurements) < M1206_MINIMUM_REPLICATES_PER_ARM
            or len(self.perturbed_measurements) < M1206_MINIMUM_REPLICATES_PER_ARM
        ):
            raise ValueError("typed perturbations require at least three replicates per arm")
        if self.baseline_measurements and self.quality_weight <= 0.0:
            raise ValueError("typed perturbations require a positive quality weight")
        if (
            self.status is PerturbationStatus.SUPPORTED
            and self.source_artifact.digest == _DERIVED_DIGEST_SENTINEL
        ):
            raise ValueError("supported perturbation requires non-placeholder source evidence")
        if self.status is PerturbationStatus.SUPPORTED and not self.evidence:
            raise ValueError("supported perturbation requires evidence")
        # Counter-evidence is allowed, but a caller must not label an
        # unsupported perturbation as ordinary positive evidence.
        if (
            self.status is not PerturbationStatus.SUPPORTED
            and self.evidence
            and any(item.role == "evidence" for item in self.evidence)
        ):
            raise ValueError("unsupported perturbation cannot carry positive evidence")
        return self


class PerturbationResponse(FrozenModel):
    scenario_id: Identifier
    status: PerturbationResponseStatus
    metric: SensitivityMetric
    baseline_response: FiniteFloat
    perturbed_response: FiniteFloat
    delta: FiniteFloat
    envelope_lower: FiniteFloat
    envelope_upper: FiniteFloat
    bounded: Literal[True] = True
    raw_effect_delta: FiniteFloat | None = None
    sensitivity_standard_error: FiniteFloat | None = Field(default=None, gt=0.0)
    replicate_count: int | None = Field(default=None, ge=0, le=M1206_MAX_REPLICATES * 2)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1206_MAX_EVIDENCE)

    @model_validator(mode="after")
    def response_is_bounded_and_consistent(self) -> PerturbationResponse:
        numeric = (
            self.baseline_response,
            self.perturbed_response,
            self.delta,
            self.envelope_lower,
            self.envelope_upper,
            self.raw_effect_delta,
            self.sensitivity_standard_error,
        )
        if any(value is not None and not isfinite(float(value)) for value in numeric):
            raise ValueError("response values must be finite numbers")
        if self.envelope_lower >= self.envelope_upper:
            raise ValueError("response envelope must be ordered")
        if not self.envelope_lower <= self.perturbed_response <= self.envelope_upper:
            raise ValueError("perturbed response is outside declared envelope")
        if not self.envelope_lower <= self.baseline_response <= self.envelope_upper:
            raise ValueError("baseline response is outside declared envelope")
        if abs(self.delta - (self.perturbed_response - self.baseline_response)) > _DELTA_TOLERANCE:
            raise ValueError("response delta must match baseline and perturbed values")
        if self.status is PerturbationResponseStatus.EVALUATED and not self.evidence:
            raise ValueError("evaluated perturbation response requires evidence")
        return self


class SensitivitySurface(FrozenModel):
    surface_id: Identifier
    axes: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1206_MAX_AXES)
    responses: tuple[PerturbationResponse, ...] = Field(
        min_length=1, max_length=M1206_MAX_RESPONSES
    )
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1206_MAX_ASSUMPTIONS)
    negative_control_passed: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1206_MAX_EVIDENCE)

    @model_validator(mode="after")
    def response_scenario_ids_are_unique(self) -> SensitivitySurface:
        ids = tuple(item.scenario_id for item in self.responses)
        if len(ids) != len(set(ids)):
            raise ValueError("sensitivity response scenario ids must be unique")
        if any(item.status is not PerturbationResponseStatus.EVALUATED for item in self.responses):
            raise ValueError("simulated sensitivity surface cannot contain unevaluable responses")
        return self


class PerturbationFinding(FrozenModel):
    finding_id: Identifier
    code: PerturbationFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1206_MAX_EVIDENCE)


class SimulateBiomarkerPanelPerturbationRequest(FrozenModel):
    """Provisional request for bounded perturbation sensitivity simulation."""

    operation: Literal["simulate_biomarker_panel_perturbation_sensitivity"] = M1206_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1206_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_consequence_result: ArtifactReference
    policy: PerturbationPolicy
    scenarios: tuple[PerturbationScenario, ...] = Field(
        min_length=1, max_length=M1206_MAX_SCENARIOS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1206_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_scenarios_are_unique_and_bounded(self) -> SimulateBiomarkerPanelPerturbationRequest:
        ids = tuple(item.scenario_id for item in self.scenarios)
        if len(ids) != len(set(ids)):
            raise ValueError("request scenario ids must be unique")
        if len(self.scenarios) > self.policy.maximum_scenarios:
            raise ValueError("request exceeds configured scenario limit")
        return self


class BiomarkerPanelPerturbationSensitivityResult(FrozenModel):
    """Bounded sensitivity surface with explicit assumptions and abstention."""

    output_type: Literal["biomarker_panel_perturbation_sensitivity"] = (
        "biomarker_panel_perturbation_sensitivity"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1206_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    request: SimulateBiomarkerPanelPerturbationRequest
    status: SimulatorStatus
    sensitivity_surface: SensitivitySurface | None = None
    findings: tuple[PerturbationFinding, ...] = Field(default=(), max_length=M1206_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    material_assumptions: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1206_MAX_ASSUMPTIONS
    )
    parent_target: Literal["biomarker_panel"] = M1206_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1206_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False
    typed_model: bool = False
    model_profile: NonEmptyStr | None = None
    bootstrap_replicates: int | None = Field(default=None, ge=16, le=M1206_MAX_BOOTSTRAP_REPLICATES)

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelPerturbationSensitivityResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is SimulatorStatus.SIMULATED:
            if (
                self.sensitivity_surface is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("simulated result requires a supported sensitivity surface")
        elif (
            self.sensitivity_surface is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no surface and safe status")
        expected_digest = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected_digest)
        elif self.result_digest != expected_digest:
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1206_CONTRACT_VERSION",
    "M1206_DEFAULT_BOOTSTRAP_REPLICATES",
    "M1206_GATE",
    "M1206_GLIOMA_MODEL_FAMILY",
    "M1206_MAX_ASSUMPTIONS",
    "M1206_MAX_AXES",
    "M1206_MAX_BOOTSTRAP_REPLICATES",
    "M1206_MAX_CANONICAL_REQUEST_BYTES",
    "M1206_MAX_CANONICAL_RESULT_BYTES",
    "M1206_MAX_EVIDENCE",
    "M1206_MAX_FINDINGS",
    "M1206_MAX_REPLICATES",
    "M1206_MAX_RESPONSES",
    "M1206_MAX_SCENARIOS",
    "M1206_MINIMUM_REPLICATES_PER_ARM",
    "M1206_MODULE_ID",
    "M1206_OPERATION",
    "M1206_OUTPUT_MEDIA_TYPE",
    "M1206_OWNER",
    "M1206_PARENT",
    "M1206_PROVISIONAL_ABI",
    "M1206_SAFETY_CLASS",
    "BiomarkerPanelPerturbationSensitivityResult",
    "PerturbationFinding",
    "PerturbationFindingCode",
    "PerturbationKind",
    "PerturbationPolicy",
    "PerturbationResponse",
    "PerturbationResponseStatus",
    "PerturbationScenario",
    "PerturbationStatus",
    "SensitivityMetric",
    "SensitivitySurface",
    "SimulateBiomarkerPanelPerturbationRequest",
    "SimulatorConfiguration",
    "SimulatorStatus",
]
