"""Provisional M10-06 uncertainty-decomposition contracts.

The M10-06 dossier requires seven explicit uncertainty dimensions, a
sensitivity envelope, calibrated nominal coverage, and safe abstention.  It
does not freeze the M10-05 handoff ABI, operation, endpoint, decomposition
representation, or media type.  Every symbol here is therefore provisional
scaffolding pending owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m10_06.canonical import (
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


class UncertaintyDecomposition(FrozenModel):
    """Typed seven-component decomposition with no hidden residual bucket."""

    decomposition_id: Identifier
    components: tuple[UncertaintyComponent, ...] = Field(
        min_length=M1006_MAX_COMPONENTS,
        max_length=M1006_MAX_COMPONENTS,
    )
    method: NonEmptyStr
    model_reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1006_MAX_EVIDENCE)

    @model_validator(mode="after")
    def component_set_is_closed(self) -> UncertaintyDecomposition:
        dimensions = tuple(item.dimension for item in self.components)
        if len(set(dimensions)) != M1006_MAX_COMPONENTS or set(dimensions) != set(
            UncertaintyDimension
        ):
            raise ValueError("uncertainty decomposition must contain all seven dimensions once")
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
        return self


class UncertaintyFinding(FrozenModel):
    finding_id: Identifier
    code: UncertaintyFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1006_MAX_EVIDENCE)


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
        if self.integrator_result.media_type != M1006_M1005_RESULT_MEDIA_TYPE:
            raise ValueError("uncertainty request must bind the provisional M10-05 result")
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
]
