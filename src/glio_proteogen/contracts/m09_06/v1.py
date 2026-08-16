"""Provisional M09-06 uncertainty decomposition contracts.

The M09-06 dossier specifies seven uncertainty dimensions, sensitivity
exposure, nominal coverage, and safe abstention.  It does not freeze the
M09-05 handoff ABI, operation, endpoint, decomposition representation, or
media type.  Every symbol here is reviewable scaffolding and is explicitly
provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m09_06.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M09-06 dossier slice.
M0906_MODULE_ID: Final = "GLIO-PROTEOGEN-M09-06"
M0906_OPERATION: Final = "decompose_complex_activity_uncertainty"
M0906_CONTRACT_VERSION: Final = "0.1.0-provisional"
M0906_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-06+json"
M0906_M0905_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m09-05+json"
M0906_PARENT: Final = "complex_activity"
M0906_OWNER: Final = "Clinical science"
M0906_SAFETY_CLASS: Final = "S2"
M0906_GATE: Final = "G2"
M0906_PROVISIONAL_ABI: Final = True
M0906_MAX_COMPONENTS: Final = 7
M0906_MAX_EVIDENCE: Final = 64
M0906_MAX_FINDINGS: Final = 64
M0906_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0906_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0906_BENCHMARK_ITERATIONS: Final = 10
M0906_MEAN_BUDGET_NS: Final = 2_000_000_000
M0906_P95_BUDGET_NS: Final = 3_000_000_000
M0906_NOMINAL_COVERAGE: Final = 0.9
M0906_MIN_COVERAGE: Final = 0.85
M0906_MAX_COVERAGE: Final = 0.95
M0906_EVIDENCE_CLAIM: Final = (
    "Caller-declared M09-05 integrator and uncertainty evidence; issuer authority "
    "is not authenticated."
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


class UncertaintyDecompositionReplayReason(StrEnum):
    """Stable reason codes for canonical replay verification."""

    VERIFIED = "verified"
    INVALID_RESULT = "invalid_result"
    DIGEST_MISMATCH = "digest_mismatch"
    NON_CANONICAL = "non_canonical"
    OVERSIZED = "oversized"


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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0906_MAX_EVIDENCE)


class UncertaintyDecomposition(FrozenModel):
    """Typed seven-component decomposition with no hidden residual bucket."""

    decomposition_id: Identifier
    components: tuple[UncertaintyComponent, ...] = Field(
        min_length=M0906_MAX_COMPONENTS,
        max_length=M0906_MAX_COMPONENTS,
    )
    method: NonEmptyStr
    model_reference: ArtifactReference
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0906_MAX_EVIDENCE)

    @model_validator(mode="after")
    def component_set_is_closed(self) -> UncertaintyDecomposition:
        dimensions = tuple(item.dimension for item in self.components)
        if len(set(dimensions)) != M0906_MAX_COMPONENTS or set(dimensions) != set(
            UncertaintyDimension
        ):
            raise ValueError("uncertainty decomposition must contain all seven dimensions once")
        return self


class SensitivityEnvelope(FrozenModel):
    """Explicit sensitivity envelope; unavailable coverage is not zero."""

    status: SensitivityEnvelopeStatus
    nominal_coverage: float = Field(default=M0906_NOMINAL_COVERAGE, ge=0.0, le=1.0)
    lower_bound: float | None = Field(default=None, ge=0.0, le=1.0)
    upper_bound: float | None = Field(default=None, ge=0.0, le=1.0)
    observed_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0906_MAX_EVIDENCE)

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
            if not M0906_MIN_COVERAGE <= observed <= M0906_MAX_COVERAGE:
                raise ValueError(
                    "observed coverage must satisfy the provisional 85-95 percent gate"
                )
            if self.nominal_coverage != M0906_NOMINAL_COVERAGE:
                raise ValueError("sensitivity envelope requires nominal 90 percent coverage")
        elif (
            self.lower_bound is not None
            or self.upper_bound is not None
            or self.observed_coverage is not None
        ):
            raise ValueError("non-evaluated sensitivity cannot carry coverage values")
        return self


class DecomposeComplexActivityUncertaintyVerification(FrozenModel):
    """Content and deterministic replay status for one result envelope."""

    content_verified: bool
    deterministic_verified: bool
    verified: bool
    result_digest: Sha256Digest | None = None
    reason: UncertaintyDecompositionReplayReason

    @model_validator(mode="after")
    def verification_flags_are_closed(
        self,
    ) -> DecomposeComplexActivityUncertaintyVerification:
        expected = self.content_verified and self.deterministic_verified
        if self.verified != expected:
            raise ValueError("verified must equal content and deterministic verification")
        if self.verified != (self.result_digest is not None):
            raise ValueError("verified results must carry a result digest only")
        return self


class UncertaintyDecompositionPolicy(FrozenModel):
    """Locked estimator and calibration declaration; no implicit defaults."""

    policy_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    nominal_coverage: float = Field(default=M0906_NOMINAL_COVERAGE, ge=0.0, le=1.0)
    calibration_reference: ArtifactReference
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0906_MAX_EVIDENCE)

    @model_validator(mode="after")
    def nominal_coverage_is_locked(self) -> UncertaintyDecompositionPolicy:
        if self.nominal_coverage != M0906_NOMINAL_COVERAGE:
            raise ValueError("uncertainty policy requires nominal 90 percent coverage")
        return self


class UncertaintyFinding(FrozenModel):
    finding_id: Identifier
    code: UncertaintyFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0906_MAX_EVIDENCE)


class DecomposeComplexActivityUncertaintyRequest(FrozenModel):
    """Provisional request ABI bound to the M09-05 integrator result."""

    operation: Literal["decompose_complex_activity_uncertainty"] = M0906_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M0906_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    integrator_result: ArtifactReference
    policy: UncertaintyDecompositionPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0906_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> DecomposeComplexActivityUncertaintyRequest:
        if self.integrator_result.media_type != M0906_M0905_RESULT_MEDIA_TYPE:
            raise ValueError("uncertainty request must bind the provisional M09-05 result")
        return self


class ComplexActivityUncertaintyDecompositionResult(FrozenModel):
    """Typed uncertainty and sensitivity output with fail-closed status."""

    output_type: Literal["complex_activity_uncertainty_decomposition"] = (
        "complex_activity_uncertainty_decomposition"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M0906_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: DecomposeComplexActivityUncertaintyRequest
    status: UncertaintyDecompositionStatus
    decomposition: UncertaintyDecomposition | None = None
    sensitivity_envelope: SensitivityEnvelope
    findings: tuple[UncertaintyFinding, ...] = Field(default=(), max_length=M0906_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M0906_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M0906_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityUncertaintyDecompositionResult:
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
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding ids must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M0906_BENCHMARK_ITERATIONS",
    "M0906_CONTRACT_VERSION",
    "M0906_EVIDENCE_CLAIM",
    "M0906_GATE",
    "M0906_M0905_RESULT_MEDIA_TYPE",
    "M0906_MAX_CANONICAL_REQUEST_BYTES",
    "M0906_MAX_CANONICAL_RESULT_BYTES",
    "M0906_MAX_COMPONENTS",
    "M0906_MAX_COVERAGE",
    "M0906_MAX_EVIDENCE",
    "M0906_MAX_FINDINGS",
    "M0906_MEAN_BUDGET_NS",
    "M0906_MIN_COVERAGE",
    "M0906_MODULE_ID",
    "M0906_NOMINAL_COVERAGE",
    "M0906_OPERATION",
    "M0906_OUTPUT_MEDIA_TYPE",
    "M0906_OWNER",
    "M0906_P95_BUDGET_NS",
    "M0906_PARENT",
    "M0906_PROVISIONAL_ABI",
    "M0906_SAFETY_CLASS",
    "ComplexActivityUncertaintyDecompositionResult",
    "DecomposeComplexActivityUncertaintyRequest",
    "DecomposeComplexActivityUncertaintyVerification",
    "SensitivityEnvelope",
    "SensitivityEnvelopeStatus",
    "UncertaintyComponent",
    "UncertaintyDecomposition",
    "UncertaintyDecompositionPolicy",
    "UncertaintyDecompositionReplayReason",
    "UncertaintyDecompositionStatus",
    "UncertaintyDimension",
    "UncertaintyFinding",
    "UncertaintyFindingCode",
]
