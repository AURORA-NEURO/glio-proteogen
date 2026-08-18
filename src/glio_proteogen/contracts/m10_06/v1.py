"""Provisional M10-06 uncertainty-decomposition contracts.

The M10-06 dossier requires seven explicit uncertainty dimensions, a
sensitivity envelope, calibrated nominal coverage, and safe abstention.  It
does not freeze the M10-05 handoff ABI, operation, endpoint, decomposition
representation, or media type.  Every symbol here is therefore provisional
scaffolding pending owner confirmation.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m10_06.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M10-06 dossier slice.
M1006_MODULE_ID: Final = "GLIO-PROTEOGEN-M10-06"
M1006_OPERATION: Final = "decompose_protein_rna_discordance_uncertainty"
M1006_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1006_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-06+json"
M1006_M1005_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-05+json"
M1006_PARENT: Final = "protein_rna_discordance"
M1006_OWNER: Final = "Data engineering"
M1006_SAFETY_CLASS: Final = "S2"
M1006_GATE: Final = "G2"
M1006_PROVISIONAL_ABI: Final = True
M1006_MAX_COMPONENTS: Final = 7
M1006_MAX_EVIDENCE: Final = 64
M1006_MAX_FINDINGS: Final = 64
M1006_MIN_COMPONENTS: Final = 7
M1006_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1006_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1006_NOMINAL_COVERAGE: Final = 0.9
M1006_MIN_COVERAGE: Final = 0.85
M1006_MAX_COVERAGE: Final = 0.95
M1006_EVIDENCE_CLAIM: Final = (
    "Caller-declared M10-05 constraint-integrator and uncertainty evidence; issuer "
    "authority is not authenticated."
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
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class UncertaintyComponent(FrozenModel):
    """One explicit uncertainty component; missing dimensions are not zero."""

    dimension: UncertaintyDimension
    estimate: UncertaintyEstimate
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1006_MAX_EVIDENCE)

    @model_validator(mode="after")
    def evidence_roles_are_explicit(self) -> UncertaintyComponent:
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("uncertainty component evidence must use the evidence role")
        return self


class UncertaintyDecomposition(FrozenModel):
    """Typed seven-component decomposition with no hidden residual bucket."""

    decomposition_id: Identifier
    components: tuple[UncertaintyComponent, ...] = Field(
        min_length=M1006_MIN_COMPONENTS,
        max_length=M1006_MIN_COMPONENTS,
    )
    method: NonEmptyStr
    model_reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1006_MAX_EVIDENCE)

    @model_validator(mode="after")
    def component_set_is_closed(self) -> UncertaintyDecomposition:
        dimensions = tuple(item.dimension for item in self.components)
        if len(set(dimensions)) != M1006_MIN_COMPONENTS or set(dimensions) != set(
            UncertaintyDimension
        ):
            raise ValueError("uncertainty decomposition must contain all seven dimensions once")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("decomposition evidence must use the evidence role")
        return self


class SensitivityEnvelope(FrozenModel):
    """Explicit sensitivity envelope; unavailable coverage is not zero."""

    status: SensitivityEnvelopeStatus
    nominal_coverage: float = Field(default=M1006_NOMINAL_COVERAGE, ge=0.0, le=1.0)
    lower_bound: float | None = None
    upper_bound: float | None = None
    observed_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1006_MAX_EVIDENCE)

    @model_validator(mode="after")
    def envelope_shape_is_closed(self) -> SensitivityEnvelope:
        values = (
            self.nominal_coverage,
            self.lower_bound,
            self.upper_bound,
            self.observed_coverage,
        )
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("sensitivity coverage values must be finite")
        if self.status is SensitivityEnvelopeStatus.EVALUATED:
            lower = self.lower_bound
            upper = self.upper_bound
            observed = self.observed_coverage
            if lower is None or upper is None or observed is None:
                raise ValueError("evaluated sensitivity requires bounds and observed coverage")
            if lower > upper:
                raise ValueError("sensitivity bounds are not ordered")
            if not M1006_MIN_COVERAGE <= observed <= M1006_MAX_COVERAGE:
                raise ValueError(
                    "observed coverage must satisfy the provisional 85-95 percent gate"
                )
            if self.nominal_coverage != M1006_NOMINAL_COVERAGE:
                raise ValueError("sensitivity envelope requires nominal 90 percent coverage")
        elif (
            self.lower_bound is not None
            or self.upper_bound is not None
            or self.observed_coverage is not None
        ):
            raise ValueError("non-evaluated sensitivity cannot carry coverage values")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("sensitivity evidence must use the evidence role")
        return self


class UncertaintyDecompositionPolicy(FrozenModel):
    """Locked estimator and calibration declaration; no implicit defaults."""

    policy_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    nominal_coverage: float = Field(default=M1006_NOMINAL_COVERAGE, ge=0.0, le=1.0)
    calibration_reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1006_MAX_EVIDENCE)

    @model_validator(mode="after")
    def nominal_coverage_is_locked(self) -> UncertaintyDecompositionPolicy:
        if self.nominal_coverage != M1006_NOMINAL_COVERAGE:
            raise ValueError("uncertainty policy requires nominal 90 percent coverage")
        if not math.isfinite(self.nominal_coverage):
            raise ValueError("uncertainty policy coverage must be finite")
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("uncertainty policy evidence must use the evidence role")
        return self


class UncertaintyFinding(FrozenModel):
    finding_id: Identifier
    code: UncertaintyFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1006_MAX_EVIDENCE)

    @model_validator(mode="after")
    def evidence_roles_are_explicit(self) -> UncertaintyFinding:
        if any(item.role != "evidence" for item in self.evidence):
            raise ValueError("uncertainty finding evidence must use the evidence role")
        return self


class DecomposeProteinRnaDiscordanceUncertaintyRequest(FrozenModel):
    """Provisional request ABI bound to the complete M10-05 result."""

    operation: Literal["decompose_protein_rna_discordance_uncertainty"] = M1006_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1006_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    integrator_result: ArtifactReference
    policy: UncertaintyDecompositionPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1006_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> DecomposeProteinRnaDiscordanceUncertaintyRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request_id must match request_id")
        if self.integrator_result.media_type != M1006_M1005_RESULT_MEDIA_TYPE:
            raise ValueError("uncertainty request must bind the provisional M10-05 result")
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("source artifacts must have unique identifiers")
        return self


class ProteinRnaDiscordanceUncertaintyDecompositionResult(FrozenModel):
    """Typed uncertainty and sensitivity output with fail-closed status."""

    output_type: Literal["protein_rna_discordance_uncertainty_decomposition"] = (
        "protein_rna_discordance_uncertainty_decomposition"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1006_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: DecomposeProteinRnaDiscordanceUncertaintyRequest
    status: UncertaintyDecompositionStatus
    decomposition: UncertaintyDecomposition | None = None
    sensitivity_envelope: SensitivityEnvelope
    findings: tuple[UncertaintyFinding, ...] = Field(default=(), max_length=M1006_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1006_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1006_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("every result requires evidence references with the evidence role")
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
        if (
            self.status is UncertaintyDecompositionStatus.ABSTAINED
            and not self.human_review_required
        ):
            raise ValueError("abstention requires human review acknowledgement")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Return explicit non-estimable dimensions before calibration is locked."""

    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "The provisional M10-06 engine has no owner-locked calibration, transport "
            "envelope, or supported decomposition model."
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
            "Missing or unsupported evidence is never converted into a negative finding.",
        ),
    )


def expected_provenance(
    request: DecomposeProteinRnaDiscordanceUncertaintyRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project all seven caller controls and immutable uncertainty inputs."""

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
        module_id=M1006_MODULE_ID,
        module_version=M1006_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.integrator_result.digest,
            request.policy.calibration_reference.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=request.policy.calibration_reference.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M1006_CONTRACT_VERSION",
    "M1006_EVIDENCE_CLAIM",
    "M1006_GATE",
    "M1006_M1005_RESULT_MEDIA_TYPE",
    "M1006_MAX_CANONICAL_REQUEST_BYTES",
    "M1006_MAX_CANONICAL_RESULT_BYTES",
    "M1006_MAX_COMPONENTS",
    "M1006_MAX_COVERAGE",
    "M1006_MAX_EVIDENCE",
    "M1006_MAX_FINDINGS",
    "M1006_MIN_COMPONENTS",
    "M1006_MIN_COVERAGE",
    "M1006_MODULE_ID",
    "M1006_NOMINAL_COVERAGE",
    "M1006_OPERATION",
    "M1006_OUTPUT_MEDIA_TYPE",
    "M1006_OWNER",
    "M1006_PARENT",
    "M1006_PROVISIONAL_ABI",
    "M1006_SAFETY_CLASS",
    "DecomposeProteinRnaDiscordanceUncertaintyRequest",
    "ProteinRnaDiscordanceUncertaintyDecompositionResult",
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
