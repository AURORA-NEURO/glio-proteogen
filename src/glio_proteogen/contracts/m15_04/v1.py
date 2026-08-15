"""Provisional M15-04 network/state/mechanism inference contracts.

The M15-04 dossier requires a mechanism posterior or state estimate with
explicit assumptions, alternatives, counter-evidence, typed uncertainty, and
safe abstention. The public ABI is provisional pending owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m15_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M15-04 dossier slice.
M1504_MODULE_ID: Final = "GLIO-PROTEOGEN-M15-04"
M1504_OPERATION: Final = "infer_complex_activity_mechanism"
M1504_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1504_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-04+json"
M1504_M1501_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-01+json"
M1504_PARENT: Final = "complex_activity"
M1504_OWNER: Final = "Computational biology"
M1504_SAFETY_CLASS: Final = "S2"
M1504_GATE: Final = "G2"
M1504_PROVISIONAL_ABI: Final = True
M1504_MAX_ESTIMATES: Final = 512
M1504_MAX_ASSUMPTIONS: Final = 64
M1504_MAX_ALTERNATIVES: Final = 64
M1504_MAX_EVIDENCE: Final = 64
M1504_MAX_FINDINGS: Final = 64
M1504_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1504_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1504_EVIDENCE_CLAIM: Final = (
    "Caller-declared M15-01 hypothesis and M15-04 mechanism-inference evidence; "
    "issuer authority is not authenticated."
)


class MechanismEstimateKind(StrEnum):
    POSTERIOR = "posterior"
    STATE = "state"


class MechanismInferenceStatus(StrEnum):
    INFERRED = "inferred"
    ABSTAINED = "abstained"


class MechanismFindingCode(StrEnum):
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    COUNTER_EVIDENCE_REQUIRED = "counter_evidence_required"
    MODEL_NOT_CALIBRATED = "model_not_calibrated"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class MechanismInferenceConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    model_reference: ArtifactReference
    calibration_reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1504_MAX_EVIDENCE)


class MechanismEstimate(FrozenModel):
    """Posterior or state estimate with explicit counter-evidence."""

    estimate_id: Identifier
    mechanism_id: Identifier
    label: NonEmptyStr
    kind: MechanismEstimateKind
    posterior_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    lower_bound: float | None = Field(default=None, ge=0.0, le=1.0)
    upper_bound: float | None = Field(default=None, ge=0.0, le=1.0)
    state_value: NonEmptyStr | None = None
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1504_MAX_ASSUMPTIONS)
    alternatives: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1504_MAX_ALTERNATIVES)
    counter_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1504_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1504_MAX_EVIDENCE)

    @model_validator(mode="after")
    def estimate_shape_is_closed(self) -> MechanismEstimate:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        if self.kind is MechanismEstimateKind.POSTERIOR:
            if (
                self.posterior_probability is None
                or self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or not self.lower_bound <= self.posterior_probability <= self.upper_bound
                or self.state_value is not None
            ):
                raise ValueError("posterior estimate requires ordered bounds and probability")
        elif self.state_value is None or self.posterior_probability is not None or has_interval:
            raise ValueError("state estimate requires state value without posterior bounds")
        return self


class MechanismFinding(FrozenModel):
    finding_id: Identifier
    code: MechanismFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1504_MAX_EVIDENCE)


class InferComplexActivityMechanismRequest(FrozenModel):
    """Provisional request bound to the M15-01 hypothesis registry."""

    operation: Literal["infer_complex_activity_mechanism"] = M1504_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1504_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    hypothesis_registry_result: ArtifactReference
    configuration: MechanismInferenceConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1504_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> InferComplexActivityMechanismRequest:
        if self.hypothesis_registry_result.media_type != M1504_M1501_RESULT_MEDIA_TYPE:
            raise ValueError("mechanism request must bind the provisional M15-01 result")
        return self


class ComplexActivityMechanismInferenceResult(FrozenModel):
    """Mechanism estimates with counter-evidence and explicit abstention."""

    output_type: Literal["complex_activity_mechanism_inference"] = (
        "complex_activity_mechanism_inference"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1504_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: InferComplexActivityMechanismRequest
    status: MechanismInferenceStatus
    estimates: tuple[MechanismEstimate, ...] = Field(default=(), max_length=M1504_MAX_ESTIMATES)
    findings: tuple[MechanismFinding, ...] = Field(default=(), max_length=M1504_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M1504_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1504_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityMechanismInferenceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        estimate_ids = tuple(item.estimate_id for item in self.estimates)
        if len(estimate_ids) != len(set(estimate_ids)):
            raise ValueError("mechanism estimate ids must be unique")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("mechanism finding ids must be unique")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("mechanism result requires evidence references")
        if self.status is MechanismInferenceStatus.INFERRED:
            if (
                not self.estimates
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.human_review_required
            ):
                raise ValueError("inferred result requires supported mechanism estimates")
        elif (
            self.estimates
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no estimates, safe status, and review")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, supported: bool) -> UncertaintyProfile:
    """Expose all seven uncertainty dimensions for mechanism inference."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "Caller-declared configuration, calibrated support, counter-evidence, and "
            "structure-aware proteoform inference are within the provisional domain."
            if supported
            else (
                "At least one upstream, calibration, support, or mechanism input "
                "was not safely evaluable."
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
            "Bayesian/state-space/mechanistic, curated baseline, and orthogonal consensus "
            "architectures remain explicit; negative controls gate promotion.",
        ),
    )


def expected_provenance(
    request: InferComplexActivityMechanismRequest, request_digest: Sha256Digest
) -> ProvenanceRecord:
    """Bind request inputs and the seven caller-declared control decisions."""

    references = request.context.references
    controls = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1504_MODULE_ID,
        module_version=M1504_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.hypothesis_registry_result.digest,
            *(item.digest for item in request.source_artifacts),
        ),
        configuration_digest=request.configuration.model_reference.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


__all__ = [
    "M1504_CONTRACT_VERSION",
    "M1504_EVIDENCE_CLAIM",
    "M1504_GATE",
    "M1504_M1501_RESULT_MEDIA_TYPE",
    "M1504_MAX_ALTERNATIVES",
    "M1504_MAX_ASSUMPTIONS",
    "M1504_MAX_CANONICAL_REQUEST_BYTES",
    "M1504_MAX_CANONICAL_RESULT_BYTES",
    "M1504_MAX_ESTIMATES",
    "M1504_MAX_EVIDENCE",
    "M1504_MAX_FINDINGS",
    "M1504_MODULE_ID",
    "M1504_OPERATION",
    "M1504_OUTPUT_MEDIA_TYPE",
    "M1504_OWNER",
    "M1504_PARENT",
    "M1504_PROVISIONAL_ABI",
    "M1504_SAFETY_CLASS",
    "ComplexActivityMechanismInferenceResult",
    "InferComplexActivityMechanismRequest",
    "MechanismEstimate",
    "MechanismEstimateKind",
    "MechanismFinding",
    "MechanismFindingCode",
    "MechanismInferenceConfiguration",
    "MechanismInferenceStatus",
    "expected_provenance",
    "expected_uncertainty",
]
