"""Provisional M14-06 perturbation and sensitivity simulator contracts.

The M14-06 dossier requires in-silico perturbations, parameter sweeps,
alternative priors, assay perturbations, mechanism stress tests, sensitivity
surfaces, bounded responses, explicit assumptions, and safe abstention. The
public ABI is provisional pending owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m14_06.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M14-06 dossier slice.
M1406_MODULE_ID: Final = "GLIO-PROTEOGEN-M14-06"
M1406_OPERATION: Final = "simulate_protein_subtype_perturbations"
M1406_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1406_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-06+json"
M1406_M1405_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-05+json"
M1406_PARENT: Final = "protein_subtype"
M1406_OWNER: Final = "Bioinformatics"
M1406_SAFETY_CLASS: Final = "S2"
M1406_GATE: Final = "G2"
M1406_PROVISIONAL_ABI: Final = True
M1406_MAX_SCENARIOS: Final = 512
M1406_MAX_TARGETS: Final = 2_048
M1406_MAX_RESPONSES: Final = M1406_MAX_SCENARIOS
M1406_MAX_EVIDENCE: Final = 64
M1406_MAX_DIAGNOSTICS: Final = 128
M1406_MAX_FINDINGS: Final = 64
M1406_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1406_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1406_EVIDENCE_CLAIM: Final = (
    "Caller-declared M14-06 perturbation and sensitivity evidence; issuer "
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
    COUNTER_EVIDENCE_REQUIRED = "counter_evidence_required"
    METHOD_OUTSIDE_SUPPORT = "method_outside_support"
    INVALID_BOUNDS = "invalid_bounds"
    CONTROL_NOT_ACCEPTED = "control_not_accepted"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class PerturbationSpecification(FrozenModel):
    perturbation_id: Identifier
    kind: PerturbationKind
    target_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1406_MAX_TARGETS)
    parameter: NonEmptyStr
    baseline_value: NonEmptyStr
    perturbed_value: NonEmptyStr
    rationale: NonEmptyStr
    alternative_prior: ArtifactReference | None = None
    assay_artifact: ArtifactReference | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1406_MAX_EVIDENCE)

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
    counter_evidence: tuple[EvidenceReference, ...] = Field(
        default=(), max_length=M1406_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1406_MAX_EVIDENCE)

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
                or not self.counter_evidence
            ):
                raise ValueError(
                    "bounded response requires ordered bounds, response, and counter-evidence"
                )
        elif self.response_value is not None or has_bounds:
            raise ValueError("non-bounded response cannot carry response values")
        return self


class SensitivitySimulationConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: NonEmptyStr
    reference_artifact: ArtifactReference
    maximum_scenarios: int = Field(gt=0, le=M1406_MAX_SCENARIOS)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1406_MAX_EVIDENCE)


class SensitivitySurface(FrozenModel):
    """Versioned surface mapping every scenario to one explicit response."""

    surface_id: Identifier
    version: SemanticVersion
    baseline_result: ArtifactReference
    perturbations: tuple[PerturbationSpecification, ...] = Field(
        min_length=1, max_length=M1406_MAX_SCENARIOS
    )
    responses: tuple[SensitivityResponse, ...] = Field(min_length=1, max_length=M1406_MAX_RESPONSES)
    configuration: SensitivitySimulationConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1406_MAX_EVIDENCE)

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
        if self.baseline_result.media_type != M1406_M1405_INPUT_MEDIA_TYPE:
            raise ValueError("surface must bind the provisional M14-05 baseline result")
        return self


class SensitivityDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: SensitivityDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1406_MAX_EVIDENCE)


class SimulateProteinSubtypePerturbationsRequest(FrozenModel):
    """Provisional request ABI bound to the M14-05 upstream result."""

    operation: Literal["simulate_protein_subtype_perturbations"] = M1406_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1406_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: SensitivitySimulationConfiguration
    perturbations: tuple[PerturbationSpecification, ...] = Field(
        min_length=1, max_length=M1406_MAX_SCENARIOS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1406_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> SimulateProteinSubtypePerturbationsRequest:
        if self.upstream_result.media_type != M1406_M1405_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M14-05 upstream result")
        ids = tuple(item.perturbation_id for item in self.perturbations)
        if len(ids) != len(set(ids)):
            raise ValueError("request perturbation identifiers must be unique")
        return self


class ProteinSubtypeSensitivitySimulationResult(FrozenModel):
    """Sensitivity surface with bounded responses and explicit abstention."""

    output_type: Literal["protein_subtype_sensitivity_surface"] = (
        "protein_subtype_sensitivity_surface"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1406_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: SimulateProteinSubtypePerturbationsRequest
    status: SensitivitySimulationStatus
    surface: SensitivitySurface | None = None
    diagnostics: tuple[SensitivityDiagnostic, ...] = Field(
        min_length=1, max_length=M1406_MAX_DIAGNOSTICS
    )
    findings: tuple[SensitivityFindingCode, ...] = Field(default=(), max_length=M1406_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M1406_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1406_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeSensitivitySimulationResult:
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
                or any(
                    item.status in unsafe_statuses or not item.counter_evidence
                    for item in self.surface.responses
                )
            ):
                raise ValueError("simulated result requires supported bounded responses")
        elif (
            self.surface is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no surface and safe status")
        if self.status is SensitivitySimulationStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstention requires human review acknowledgement")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, supported: bool) -> UncertaintyProfile:
    """Construct all seven uncertainty dimensions without hiding abstention."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "Locked perturbation configuration and bounded response evidence are present; "
            "transport beyond the declared support domain is not inferred."
            if supported
            else "Perturbation support, quality, or controls were not safely evaluable."
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
            "Sensitivity, assumptions, alternative priors, and counter-evidence are retained.",
            "Unsupported or missing evidence is never converted into a negative response.",
        ),
    )


def expected_provenance(
    request: SimulateProteinSubtypePerturbationsRequest,
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
        module_id=M1406_MODULE_ID,
        module_version=M1406_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
            *(item.evidence_digest for item in decisions),
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M1406_CONTRACT_VERSION",
    "M1406_EVIDENCE_CLAIM",
    "M1406_GATE",
    "M1406_M1405_INPUT_MEDIA_TYPE",
    "M1406_MAX_CANONICAL_REQUEST_BYTES",
    "M1406_MAX_CANONICAL_RESULT_BYTES",
    "M1406_MAX_DIAGNOSTICS",
    "M1406_MAX_EVIDENCE",
    "M1406_MAX_FINDINGS",
    "M1406_MAX_RESPONSES",
    "M1406_MAX_SCENARIOS",
    "M1406_MAX_TARGETS",
    "M1406_MODULE_ID",
    "M1406_OPERATION",
    "M1406_OUTPUT_MEDIA_TYPE",
    "M1406_OWNER",
    "M1406_PARENT",
    "M1406_PROVISIONAL_ABI",
    "M1406_SAFETY_CLASS",
    "PerturbationKind",
    "PerturbationResponseStatus",
    "PerturbationSpecification",
    "ProteinSubtypeSensitivitySimulationResult",
    "SensitivityDiagnostic",
    "SensitivityDiagnosticStatus",
    "SensitivityFindingCode",
    "SensitivityResponse",
    "SensitivitySimulationConfiguration",
    "SensitivitySimulationStatus",
    "SensitivitySurface",
    "SimulateProteinSubtypePerturbationsRequest",
    "expected_provenance",
    "expected_uncertainty",
]
