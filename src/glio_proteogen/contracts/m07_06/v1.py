"""Provisional M07-06 uncertainty-decomposition contracts.

The dossier specifies seven uncertainty dimensions, sensitivity exposure, and
safe abstention, but does not freeze the M07-05 handoff ABI, estimator,
calibration artifact, operation, endpoint, or media type.  Every symbol here
is reviewable scaffolding and is explicitly provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m07_06.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M07-06 dossier slice.
M0706_MODULE_ID: Final = "GLIO-PROTEOGEN-M07-06"
M0706_OPERATION: Final = "decompose_copy_number_dosage_uncertainty"
M0706_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0706_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-06+json"
M0706_CONSTRAINT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m07-05+json"
M0706_PARENT: Final = "proteotype"
M0706_OWNER: Final = "ML engineering"
M0706_SAFETY_CLASS: Final = "S2"
M0706_GATE: Final = "G2"
M0706_MAX_COMPONENTS: Final = 7
M0706_MAX_EVIDENCE: Final = 32
M0706_MAX_FINDINGS: Final = 32
M0706_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0706_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0706_NOMINAL_COVERAGE: Final = 0.9
M0706_MIN_COVERAGE: Final = 0.85
M0706_MAX_COVERAGE: Final = 0.95
M0706_EVIDENCE_CLAIM: Final = (
    "Caller-declared M07-05 constraint and uncertainty evidence; "
    "issuer authority is not authenticated."
)


class UncertaintyDimension(StrEnum):
    MEASUREMENT = "measurement"
    SAMPLING = "sampling"
    PARAMETER = "parameter"
    MODEL_FORM = "model_form"
    IDENTIFICATION = "identification"
    SUPPORT = "support"
    TRANSPORT = "transport"


class SensitivityEnvelopeStatus(StrEnum):
    EVALUATED = "evaluated"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class UncertaintyDecompositionStatus(StrEnum):
    DECOMPOSED = "decomposed"
    ABSTAINED = "abstained"


class UncertaintyFindingCode(StrEnum):
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    CALIBRATION_NOT_LOCKED = "calibration_not_locked"
    SENSITIVITY_NOT_EVALUABLE = "sensitivity_not_evaluable"


class UncertaintyComponent(FrozenModel):
    """One explicit uncertainty component; no missing dimension is zero."""

    dimension: UncertaintyDimension
    estimate: UncertaintyEstimate
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0706_MAX_EVIDENCE)


class UncertaintyDecomposition(FrozenModel):
    """Typed seven-component decomposition with no hidden residual bucket."""

    decomposition_id: Identifier
    components: tuple[UncertaintyComponent, ...] = Field(
        min_length=M0706_MAX_COMPONENTS,
        max_length=M0706_MAX_COMPONENTS,
    )
    method: NonEmptyStr
    model_reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0706_MAX_EVIDENCE)

    @model_validator(mode="after")
    def component_set_is_closed(self) -> UncertaintyDecomposition:
        dimensions = tuple(item.dimension for item in self.components)
        if len(set(dimensions)) != M0706_MAX_COMPONENTS or set(dimensions) != set(
            UncertaintyDimension
        ):
            raise ValueError("uncertainty decomposition must contain all seven dimensions once")
        return self


class SensitivityEnvelope(FrozenModel):
    """Explicit sensitivity envelope; unavailable coverage is not zero."""

    status: SensitivityEnvelopeStatus
    nominal_coverage: float = Field(ge=0.0, le=1.0)
    lower_bound: float | None = None
    upper_bound: float | None = None
    observed_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0706_MAX_EVIDENCE)

    @model_validator(mode="after")
    def envelope_shape_is_closed(self) -> SensitivityEnvelope:
        if self.status is SensitivityEnvelopeStatus.EVALUATED:
            lower = self.lower_bound
            upper = self.upper_bound
            observed = self.observed_coverage
            if lower is None or upper is None or observed is None:
                raise ValueError("evaluated sensitivity requires bounds and observed coverage")
            if lower > upper:
                raise ValueError("sensitivity bounds are not ordered")
            if not M0706_MIN_COVERAGE <= observed <= M0706_MAX_COVERAGE:
                raise ValueError(
                    "observed coverage must satisfy the provisional 85-95 percent gate"
                )
        elif (
            self.lower_bound is not None
            or self.upper_bound is not None
            or self.observed_coverage is not None
        ):
            raise ValueError("non-evaluated sensitivity cannot carry coverage values")
        return self


class UncertaintyDecompositionPolicy(FrozenModel):
    """Locked estimator and calibration declaration; no implicit defaults."""

    policy_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    nominal_coverage: float = Field(default=M0706_NOMINAL_COVERAGE, ge=0.0, le=1.0)
    calibration_reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0706_MAX_EVIDENCE)


class UncertaintyFinding(FrozenModel):
    finding_id: Identifier
    code: UncertaintyFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0706_MAX_EVIDENCE)


class DecomposeCopyNumberDosageUncertaintyRequest(FrozenModel):
    """Provisional request ABI bound to the complete M07-05 result reference."""

    operation: Literal["decompose_copy_number_dosage_uncertainty"] = M0706_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0706_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    constraint_result: ArtifactReference
    policy: UncertaintyDecompositionPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0706_MAX_EVIDENCE,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> DecomposeCopyNumberDosageUncertaintyRequest:
        if self.constraint_result.media_type != M0706_CONSTRAINT_MEDIA_TYPE:
            raise ValueError("uncertainty request must bind the provisional M07-05 result")
        if self.policy.nominal_coverage != M0706_NOMINAL_COVERAGE:
            raise ValueError("provisional sensitivity gate requires nominal 90 percent coverage")
        return self


class CopyNumberDosageUncertaintyDecompositionResult(FrozenModel):
    """Typed uncertainty and sensitivity output with fail-closed release status."""

    output_type: Literal["copy_number_dosage_uncertainty_decomposition"] = (
        "copy_number_dosage_uncertainty_decomposition"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0706_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: DecomposeCopyNumberDosageUncertaintyRequest
    status: UncertaintyDecompositionStatus
    decomposition: UncertaintyDecomposition | None = None
    sensitivity_envelope: SensitivityEnvelope
    findings: tuple[UncertaintyFinding, ...] = Field(default=(), max_length=M0706_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M0706_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0706_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> CopyNumberDosageUncertaintyDecompositionResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is UncertaintyDecompositionStatus.DECOMPOSED:
            if (
                self.decomposition is None
                or self.abstention_reason is not None
                or self.sensitivity_envelope.status is not SensitivityEnvelopeStatus.EVALUATED
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("decomposed result requires calibrated supported output")
        elif (
            self.decomposition is not None
            or self.abstention_reason is None
            or self.sensitivity_envelope.status is not SensitivityEnvelopeStatus.ABSTAINED
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no decomposition and explicit safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Return an explicit seven-dimension non-estimable profile for safe abstention."""

    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="The provisional M07-06 scaffold has no owner-confirmed calibration.",
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


def expected_provenance(
    request: DecomposeCopyNumberDosageUncertaintyRequest,
    request_digest: Sha256Digest,
    policy_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project all seven caller controls into module-local provenance."""

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
        module_id=M0706_MODULE_ID,
        module_version=M0706_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(request_digest, request.constraint_result.digest),
        configuration_digest=policy_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M0706_CONSTRAINT_MEDIA_TYPE",
    "M0706_CONTRACT_VERSION",
    "M0706_EVIDENCE_CLAIM",
    "M0706_GATE",
    "M0706_MAX_CANONICAL_REQUEST_BYTES",
    "M0706_MAX_CANONICAL_RESULT_BYTES",
    "M0706_MAX_COMPONENTS",
    "M0706_MAX_COVERAGE",
    "M0706_MAX_EVIDENCE",
    "M0706_MAX_FINDINGS",
    "M0706_MIN_COVERAGE",
    "M0706_MODULE_ID",
    "M0706_NOMINAL_COVERAGE",
    "M0706_OPERATION",
    "M0706_OUTPUT_MEDIA_TYPE",
    "M0706_OWNER",
    "M0706_PARENT",
    "M0706_SAFETY_CLASS",
    "CopyNumberDosageUncertaintyDecompositionResult",
    "DecomposeCopyNumberDosageUncertaintyRequest",
    "SensitivityEnvelope",
    "SensitivityEnvelopeStatus",
    "UncertaintyComponent",
    "UncertaintyDecomposition",
    "UncertaintyDecompositionPolicy",
    "UncertaintyDecompositionStatus",
    "UncertaintyDimension",
    "UncertaintyFinding",
    "UncertaintyFindingCode",
    "expected_provenance",
    "expected_uncertainty",
]
