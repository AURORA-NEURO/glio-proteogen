"""Provisional M07-03 mature baseline-estimator contracts.

The dossier defines a transparent baseline, locked preprocessing/tuning,
uncertainty, diagnostics, and safe failure.  It does not freeze the M07-02
handoff ABI, estimator catalogue, operation, endpoint, or media type.  The
symbols below are reviewable scaffolding only and are explicitly provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m07_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M07-03 dossier slice.
M0703_MODULE_ID: Final = "GLIO-PROTEOGEN-M07-03"
M0703_OPERATION: Final = "estimate_copy_number_dosage_baseline"
M0703_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0703_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-03+json"
M0703_REPRESENTATION_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-02+json"
M0703_PARENT: Final = "proteotype"
M0703_OWNER: Final = "Scientific engineering"
M0703_SAFETY_CLASS: Final = "S2"
M0703_GATE: Final = "G1"
M0703_MAX_FEATURES: Final = 512
M0703_MAX_ESTIMATES: Final = M0703_MAX_FEATURES
M0703_MAX_DIAGNOSTICS: Final = 512
M0703_MAX_PREPROCESSING_STEPS: Final = 64
M0703_MAX_METRICS: Final = 64
M0703_MAX_EVIDENCE: Final = 32
M0703_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0703_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0703_EVIDENCE_CLAIM: Final = (
    "Caller-declared M07-02 representation and baseline evidence; "
    "issuer authority is not authenticated."
)


class BaselineEstimatorFamily(StrEnum):
    RULE_BASED = "rule_based"
    ROBUST_STATISTICAL = "robust_statistical"
    ESTABLISHED_COMPUTATIONAL = "established_computational"


class BaselineEstimateKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"


class BaselineDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class BaselineResultStatus(StrEnum):
    ESTIMATED = "estimated"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class BaselinePreprocessingPolicy(FrozenModel):
    """Locked preprocessing declaration; transformation is outside this ABI."""

    policy_id: Identifier
    version: SemanticVersion
    operations: tuple[NonEmptyStr, ...] = Field(
        min_length=1,
        max_length=M0703_MAX_PREPROCESSING_STEPS,
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0703_MAX_EVIDENCE)


class BaselineTuningRecord(FrozenModel):
    """Locked tuning declaration; no tuning is performed by the contract."""

    tuning_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    objective: NonEmptyStr
    seed: int = Field(ge=0)
    metrics: tuple[NonEmptyStr, ...] = Field(default=(), max_length=M0703_MAX_METRICS)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0703_MAX_EVIDENCE)


class MatureBaselineConfiguration(FrozenModel):
    """Versioned baseline configuration bound to the provisional M07-02 handoff."""

    configuration_id: Identifier
    version: SemanticVersion
    estimator_family: BaselineEstimatorFamily
    representation_media_type: Literal["application/vnd.glio-proteogen.m07-02+json"] = (
        M0703_REPRESENTATION_MEDIA_TYPE
    )
    preprocessing: BaselinePreprocessingPolicy
    tuning: BaselineTuningRecord
    reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0703_MAX_EVIDENCE)


class BaselineEstimate(FrozenModel):
    """One typed baseline estimate; missing or unsupported values remain explicit."""

    feature_id: Identifier
    kind: BaselineEstimateKind
    unit: NonEmptyStr
    estimate_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    category: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0703_MAX_EVIDENCE)

    @model_validator(mode="after")
    def estimate_shape_is_closed(self) -> BaselineEstimate:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        if self.kind is BaselineEstimateKind.SCALAR:
            if self.estimate_value is None or has_interval or self.category is not None:
                raise ValueError("scalar baseline estimate requires one scalar value")
        elif self.kind is BaselineEstimateKind.INTERVAL:
            if (
                self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or self.estimate_value is None
                or self.category is not None
            ):
                raise ValueError("interval baseline estimate requires ordered bounds and center")
            if not self.lower_bound <= self.estimate_value <= self.upper_bound:
                raise ValueError("interval center must lie within its bounds")
        elif self.category is None or self.estimate_value is not None or has_interval:
            raise ValueError("categorical baseline estimate requires only a category")
        return self


class BaselineDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: BaselineDiagnosticStatus
    message: NonEmptyStr
    metric_name: NonEmptyStr | None = None
    metric_value: float | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0703_MAX_EVIDENCE)


class EstimateCopyNumberDosageBaselineRequest(FrozenModel):
    """Provisional request ABI bound to the complete M07-02 representation reference."""

    operation: Literal["estimate_copy_number_dosage_baseline"] = M0703_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0703_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    representation_result: ArtifactReference
    configuration: MatureBaselineConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0703_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EstimateCopyNumberDosageBaselineRequest:
        if self.representation_result.media_type != M0703_REPRESENTATION_MEDIA_TYPE:
            raise ValueError("baseline request must bind the provisional M07-02 representation")
        if self.configuration.representation_media_type != self.representation_result.media_type:
            raise ValueError("baseline configuration does not bind the M07-02 representation")
        return self


class EstimateCopyNumberDosageBaselineResult(FrozenModel):
    """Provisional baseline result with diagnostics, uncertainty, and safe failure."""

    output_type: Literal["copy_number_dosage_baseline_estimate"] = (
        "copy_number_dosage_baseline_estimate"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0703_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EstimateCopyNumberDosageBaselineRequest
    status: BaselineResultStatus
    estimates: tuple[BaselineEstimate, ...] = Field(default=(), max_length=M0703_MAX_ESTIMATES)
    diagnostics: tuple[BaselineDiagnostic, ...] = Field(
        default=(), max_length=M0703_MAX_DIAGNOSTICS
    )
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M0703_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0703_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> EstimateCopyNumberDosageBaselineResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is BaselineResultStatus.ESTIMATED:
            if not self.estimates or self.abstention_reason is not None:
                raise ValueError("estimated result requires estimates and no abstention reason")
            if self.support_decision.status is not SupportStatus.SUPPORTED:
                raise ValueError("estimated result requires supported status")
        elif (
            self.estimates
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("non-estimated result requires no estimates and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_provenance(
    request: EstimateCopyNumberDosageBaselineRequest,
    request_digest: Sha256Digest,
    configuration_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project the seven caller controls into module-local provenance."""

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
        module_id=M0703_MODULE_ID,
        module_version=M0703_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(request_digest, request.representation_result.digest),
        configuration_digest=configuration_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def expected_uncertainty() -> UncertaintyProfile:
    """Return explicit non-estimable uncertainty for the provisional baseline."""

    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="The provisional M07-03 scaffold has no owner-confirmed calibration.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Nominal coverage is not claimed until benchmark evidence is locked.",),
    )


__all__ = [
    "M0703_CONTRACT_VERSION",
    "M0703_EVIDENCE_CLAIM",
    "M0703_GATE",
    "M0703_MAX_CANONICAL_REQUEST_BYTES",
    "M0703_MAX_CANONICAL_RESULT_BYTES",
    "M0703_MAX_DIAGNOSTICS",
    "M0703_MAX_ESTIMATES",
    "M0703_MAX_EVIDENCE",
    "M0703_MAX_FEATURES",
    "M0703_MAX_METRICS",
    "M0703_MAX_PREPROCESSING_STEPS",
    "M0703_MODULE_ID",
    "M0703_OPERATION",
    "M0703_OUTPUT_MEDIA_TYPE",
    "M0703_OWNER",
    "M0703_PARENT",
    "M0703_REPRESENTATION_MEDIA_TYPE",
    "M0703_SAFETY_CLASS",
    "BaselineDiagnostic",
    "BaselineDiagnosticStatus",
    "BaselineEstimate",
    "BaselineEstimateKind",
    "BaselineEstimatorFamily",
    "BaselinePreprocessingPolicy",
    "BaselineResultStatus",
    "BaselineTuningRecord",
    "EstimateCopyNumberDosageBaselineRequest",
    "EstimateCopyNumberDosageBaselineResult",
    "MatureBaselineConfiguration",
    "expected_provenance",
    "expected_uncertainty",
]
