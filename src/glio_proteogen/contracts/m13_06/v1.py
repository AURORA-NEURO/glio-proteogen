"""Provisional M13-06 perturbation and sensitivity simulator contracts.

The dossier defines a bounded sensitivity surface and perturbation response
under the Variant-peptide channel.  The public ABI is not frozen; these types
make assumptions, bounds, negative controls, provenance, and safe abstention
explicit for the proteotype parent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m13_06.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 4576-4619.
M1306_MODULE_ID: Final = "GLIO-PROTEOGEN-M13-06"
M1306_OPERATION: Final = "simulate_proteotype_perturbation_sensitivity"
M1306_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1306_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m13-06+json"
M1306_PARENT: Final = "proteotype"
M1306_OWNER: Final = "Computational biology"
M1306_SAFETY_CLASS: Final = "S2"
M1306_GATE: Final = "G2"
M1306_PROVISIONAL_ABI: Final = True
M1306_MAX_SCENARIOS: Final = 256
M1306_MAX_RESPONSES: Final = 512
M1306_MAX_AXES: Final = 32
M1306_MAX_EVIDENCE: Final = 64
M1306_MAX_FINDINGS: Final = 64
M1306_MAX_ASSUMPTIONS: Final = 64
M1306_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1306_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
_DELTA_TOLERANCE: Final = 1e-9


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


class SimulatorConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    units_reference: ArtifactReference
    locked: Literal[True] = True
    negative_controls_required: Literal[True] = True
    bounded_responses_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1306_MAX_EVIDENCE)


class PerturbationPolicy(FrozenModel):
    maximum_scenarios: int = Field(ge=1, le=M1306_MAX_SCENARIOS)
    response_lower_bound: float
    response_upper_bound: float
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
    baseline_value: float
    perturbed_value: float
    unit: NonEmptyStr
    status: PerturbationStatus
    assumption: NonEmptyStr
    source_artifact: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1306_MAX_EVIDENCE)

    @model_validator(mode="after")
    def supported_scenario_is_evidenced(self) -> PerturbationScenario:
        if self.status is PerturbationStatus.SUPPORTED and not self.evidence:
            raise ValueError("supported perturbation requires evidence")
        return self


class PerturbationResponse(FrozenModel):
    scenario_id: Identifier
    status: PerturbationResponseStatus
    metric: SensitivityMetric
    baseline_response: float
    perturbed_response: float
    delta: float
    envelope_lower: float
    envelope_upper: float
    bounded: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1306_MAX_EVIDENCE)

    @model_validator(mode="after")
    def response_is_bounded_and_consistent(self) -> PerturbationResponse:
        if self.envelope_lower >= self.envelope_upper:
            raise ValueError("response envelope must be ordered")
        if not self.envelope_lower <= self.perturbed_response <= self.envelope_upper:
            raise ValueError("perturbed response is outside declared envelope")
        if abs(self.delta - (self.perturbed_response - self.baseline_response)) > _DELTA_TOLERANCE:
            raise ValueError("response delta must match baseline and perturbed values")
        if self.status is PerturbationResponseStatus.EVALUATED and not self.evidence:
            raise ValueError("evaluated perturbation response requires evidence")
        return self


class SensitivitySurface(FrozenModel):
    surface_id: Identifier
    axes: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1306_MAX_AXES)
    responses: tuple[PerturbationResponse, ...] = Field(
        min_length=1, max_length=M1306_MAX_RESPONSES
    )
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1306_MAX_ASSUMPTIONS)
    negative_control_passed: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1306_MAX_EVIDENCE)

    @model_validator(mode="after")
    def response_scenario_ids_are_unique(self) -> SensitivitySurface:
        ids = tuple(item.scenario_id for item in self.responses)
        if len(ids) != len(set(ids)):
            raise ValueError("sensitivity response scenario ids must be unique")
        return self


class PerturbationFinding(FrozenModel):
    finding_id: Identifier
    code: PerturbationFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1306_MAX_EVIDENCE)


class SimulateProteotypePerturbationRequest(FrozenModel):
    """Provisional request for bounded proteotype perturbation simulation."""

    operation: Literal["simulate_proteotype_perturbation_sensitivity"] = M1306_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1306_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    variant_peptide_result: ArtifactReference
    policy: PerturbationPolicy
    scenarios: tuple[PerturbationScenario, ...] = Field(
        min_length=1, max_length=M1306_MAX_SCENARIOS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1306_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_scenarios_are_unique_and_bounded(self) -> SimulateProteotypePerturbationRequest:
        ids = tuple(item.scenario_id for item in self.scenarios)
        if len(ids) != len(set(ids)):
            raise ValueError("request scenario ids must be unique")
        if len(self.scenarios) > self.policy.maximum_scenarios:
            raise ValueError("request exceeds configured scenario limit")
        return self


class ProteotypePerturbationSensitivityResult(FrozenModel):
    """Bounded proteotype sensitivity surface with explicit safe failure."""

    output_type: Literal["proteotype_perturbation_sensitivity"] = (
        "proteotype_perturbation_sensitivity"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1306_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: SimulateProteotypePerturbationRequest
    status: SimulatorStatus
    sensitivity_surface: SensitivitySurface | None = None
    findings: tuple[PerturbationFinding, ...] = Field(default=(), max_length=M1306_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    material_assumptions: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1306_MAX_ASSUMPTIONS
    )
    parent_target: Literal["proteotype"] = M1306_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1306_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypePerturbationSensitivityResult:
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
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1306_CONTRACT_VERSION",
    "M1306_GATE",
    "M1306_MAX_ASSUMPTIONS",
    "M1306_MAX_AXES",
    "M1306_MAX_CANONICAL_REQUEST_BYTES",
    "M1306_MAX_CANONICAL_RESULT_BYTES",
    "M1306_MAX_EVIDENCE",
    "M1306_MAX_FINDINGS",
    "M1306_MAX_RESPONSES",
    "M1306_MAX_SCENARIOS",
    "M1306_MODULE_ID",
    "M1306_OPERATION",
    "M1306_OUTPUT_MEDIA_TYPE",
    "M1306_OWNER",
    "M1306_PARENT",
    "M1306_PROVISIONAL_ABI",
    "M1306_SAFETY_CLASS",
    "PerturbationFinding",
    "PerturbationFindingCode",
    "PerturbationKind",
    "PerturbationPolicy",
    "PerturbationResponse",
    "PerturbationResponseStatus",
    "PerturbationScenario",
    "PerturbationStatus",
    "ProteotypePerturbationSensitivityResult",
    "SensitivityMetric",
    "SensitivitySurface",
    "SimulateProteotypePerturbationRequest",
    "SimulatorConfiguration",
    "SimulatorStatus",
]
