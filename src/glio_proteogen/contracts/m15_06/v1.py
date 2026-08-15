"""Provisional M15-06 perturbation and sensitivity simulator contracts.

The M15-06 dossier requires in-silico perturbations, parameter sweeps,
alternative priors, assay perturbations, mechanism stress tests, sensitivity
surfaces, bounded responses, explicit assumptions, and safe abstention. The
public ABI is provisional pending owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m15_06.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M15-06 dossier slice.
M1506_MODULE_ID: Final = "GLIO-PROTEOGEN-M15-06"
M1506_OPERATION: Final = "simulate_complex_activity_perturbations"
M1506_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1506_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-06+json"
M1506_M1505_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-05+json"
M1506_PARENT: Final = "complex_activity"
M1506_OWNER: Final = "ML engineering"
M1506_SAFETY_CLASS: Final = "S2"
M1506_GATE: Final = "G2"
M1506_PROVISIONAL_ABI: Final = True
M1506_MAX_SCENARIOS: Final = 512
M1506_MAX_TARGETS: Final = 2_048
M1506_MAX_RESPONSES: Final = M1506_MAX_SCENARIOS
M1506_MAX_EVIDENCE: Final = 64
M1506_MAX_DIAGNOSTICS: Final = 128
M1506_MAX_FINDINGS: Final = 64
M1506_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1506_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1506_EVIDENCE_CLAIM: Final = (
    "Caller-declared M15-06 perturbation and sensitivity evidence; issuer "
    "authority is not authenticated."
)


class PerturbationKind(StrEnum):
    IN_SILICO = "in_silico"
    PARAMETER_SWEEP = "parameter_sweep"
    ALTERNATIVE_PRIOR = "alternative_prior"
    ASSAY_PERTURBATION = "assay_perturbation"
    MECHANISM_STRESS = "mechanism_stress"


class PerturbationResponseStatus(StrEnum):
    BOUNDED = "bounded"
    OUT_OF_ENVELOPE = "out_of_envelope"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class SensitivitySimulationStatus(StrEnum):
    SIMULATED = "simulated"
    ABSTAINED = "abstained"


class SensitivityDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class SensitivityFindingCode(StrEnum):
    INPUT_INCOMPLETE = "input_incomplete"
    RESPONSE_OUT_OF_ENVELOPE = "response_out_of_envelope"
    ASSUMPTION_UNRESOLVED = "assumption_unresolved"
    NEGATIVE_CONTROL_FAILED = "negative_control_failed"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class PerturbationSpecification(FrozenModel):
    perturbation_id: Identifier
    kind: PerturbationKind
    target_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1506_MAX_TARGETS)
    parameter: NonEmptyStr
    baseline_value: NonEmptyStr
    perturbed_value: NonEmptyStr
    rationale: NonEmptyStr
    alternative_prior: ArtifactReference | None = None
    assay_artifact: ArtifactReference | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1506_MAX_EVIDENCE)

    @model_validator(mode="after")
    def perturbation_shape_is_closed(self) -> PerturbationSpecification:
        if self.baseline_value == self.perturbed_value:
            raise ValueError("perturbation baseline and perturbed values must differ")
        if self.kind is PerturbationKind.ALTERNATIVE_PRIOR and self.alternative_prior is None:
            raise ValueError("alternative-prior perturbation requires a prior artifact")
        if self.kind is PerturbationKind.ASSAY_PERTURBATION and self.assay_artifact is None:
            raise ValueError("assay perturbation requires an assay artifact")
        return self


class SensitivityResponse(FrozenModel):
    scenario_id: Identifier
    status: PerturbationResponseStatus
    response_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=64)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1506_MAX_EVIDENCE)

    @model_validator(mode="after")
    def response_bounds_are_closed(self) -> SensitivityResponse:
        has_bounds = self.lower_bound is not None or self.upper_bound is not None
        if self.status is PerturbationResponseStatus.BOUNDED:
            if (
                self.response_value is None
                or self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or not self.lower_bound <= self.response_value <= self.upper_bound
            ):
                raise ValueError("bounded response requires ordered bounds containing response")
        elif self.response_value is not None or has_bounds:
            raise ValueError("non-bounded response cannot carry response values")
        return self


class SensitivitySimulationConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: NonEmptyStr
    reference_artifact: ArtifactReference
    maximum_scenarios: int = Field(gt=0, le=M1506_MAX_SCENARIOS)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1506_MAX_EVIDENCE)


class SensitivitySurface(FrozenModel):
    """Versioned surface mapping every scenario to one explicit response."""

    surface_id: Identifier
    version: SemanticVersion
    baseline_result: ArtifactReference
    perturbations: tuple[PerturbationSpecification, ...] = Field(
        min_length=1, max_length=M1506_MAX_SCENARIOS
    )
    responses: tuple[SensitivityResponse, ...] = Field(
        min_length=1, max_length=M1506_MAX_RESPONSES
    )
    configuration: SensitivitySimulationConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1506_MAX_EVIDENCE)

    @model_validator(mode="after")
    def surface_is_closed(self) -> SensitivitySurface:
        scenario_ids = tuple(item.perturbation_id for item in self.perturbations)
        response_ids = tuple(item.scenario_id for item in self.responses)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("perturbation identifiers must be unique")
        if len(response_ids) != len(set(response_ids)):
            raise ValueError("sensitivity response identifiers must be unique")
        if set(scenario_ids) != set(response_ids):
            raise ValueError("every perturbation must have exactly one sensitivity response")
        if self.baseline_result.media_type != M1506_M1505_INPUT_MEDIA_TYPE:
            raise ValueError("surface must bind the provisional M15-05 baseline result")
        return self


class SensitivityDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: SensitivityDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1506_MAX_EVIDENCE)


class SimulateComplexActivityPerturbationsRequest(FrozenModel):
    """Provisional request ABI bound to the M15-05 upstream result."""

    operation: Literal["simulate_complex_activity_perturbations"] = M1506_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1506_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: SensitivitySimulationConfiguration
    perturbations: tuple[PerturbationSpecification, ...] = Field(
        min_length=1, max_length=M1506_MAX_SCENARIOS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1506_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> SimulateComplexActivityPerturbationsRequest:
        if self.upstream_result.media_type != M1506_M1505_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M15-05 upstream result")
        ids = tuple(item.perturbation_id for item in self.perturbations)
        if len(ids) != len(set(ids)):
            raise ValueError("request perturbation identifiers must be unique")
        return self


class ComplexActivitySensitivitySimulationResult(FrozenModel):
    """Sensitivity surface with bounded responses and explicit abstention."""

    output_type: Literal["complex_activity_sensitivity_surface"] = (
        "complex_activity_sensitivity_surface"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1506_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: SimulateComplexActivityPerturbationsRequest
    status: SensitivitySimulationStatus
    surface: SensitivitySurface | None = None
    diagnostics: tuple[SensitivityDiagnostic, ...] = Field(
        min_length=1, max_length=M1506_MAX_DIAGNOSTICS
    )
    findings: tuple[SensitivityFindingCode, ...] = Field(
        default=(), max_length=M1506_MAX_FINDINGS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M1506_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1506_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivitySensitivitySimulationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        unsafe_statuses = {
            PerturbationResponseStatus.OUT_OF_ENVELOPE,
            PerturbationResponseStatus.NOT_EVALUABLE,
            PerturbationResponseStatus.ABSTAINED,
        }
        if self.status is SensitivitySimulationStatus.SIMULATED:
            if (
                self.surface is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in unsafe_statuses for item in self.surface.responses)
            ):
                raise ValueError("simulated result requires supported bounded responses")
        elif (
            self.surface is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no surface and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1506_CONTRACT_VERSION",
    "M1506_EVIDENCE_CLAIM",
    "M1506_GATE",
    "M1506_M1505_INPUT_MEDIA_TYPE",
    "M1506_MAX_CANONICAL_REQUEST_BYTES",
    "M1506_MAX_CANONICAL_RESULT_BYTES",
    "M1506_MAX_DIAGNOSTICS",
    "M1506_MAX_EVIDENCE",
    "M1506_MAX_FINDINGS",
    "M1506_MAX_RESPONSES",
    "M1506_MAX_SCENARIOS",
    "M1506_MAX_TARGETS",
    "M1506_MODULE_ID",
    "M1506_OPERATION",
    "M1506_OUTPUT_MEDIA_TYPE",
    "M1506_OWNER",
    "M1506_PARENT",
    "M1506_PROVISIONAL_ABI",
    "M1506_SAFETY_CLASS",
    "ComplexActivitySensitivitySimulationResult",
    "PerturbationKind",
    "PerturbationResponseStatus",
    "PerturbationSpecification",
    "SensitivityDiagnostic",
    "SensitivityDiagnosticStatus",
    "SensitivityFindingCode",
    "SensitivityResponse",
    "SensitivitySimulationConfiguration",
    "SensitivitySimulationStatus",
    "SensitivitySurface",
    "SimulateComplexActivityPerturbationsRequest",
]
