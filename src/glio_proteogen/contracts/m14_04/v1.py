"""Provisional M14-04 network/state/mechanism inference contracts.

The M14-04 dossier requires a mechanism posterior or state estimate with
explicit assumptions, alternatives, counter-evidence, typed uncertainty, and
safe abstention.  The public ABI and handoff details are not frozen; all
symbols are provisional pending Clinical science owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m14_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M14-04 dossier slice.
M1404_MODULE_ID: Final = "GLIO-PROTEOGEN-M14-04"
M1404_OPERATION: Final = "infer_protein_subtype_mechanism"
M1404_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1404_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-04+json"
M1404_M1401_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m14-01+json"
M1404_PARENT: Final = "protein_subtype"
M1404_OWNER: Final = "Scientific engineering"
M1404_SAFETY_CLASS: Final = "S2"
M1404_GATE: Final = "G2"
M1404_PROVISIONAL_ABI: Final = True
M1404_MAX_ESTIMATES: Final = 512
M1404_MAX_ASSUMPTIONS: Final = 64
M1404_MAX_ALTERNATIVES: Final = 64
M1404_MAX_EVIDENCE: Final = 64
M1404_MAX_FINDINGS: Final = 64
M1404_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1404_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1404_EVIDENCE_CLAIM: Final = (
    "Caller-declared M14-01 hypothesis and M14-04 mechanism-inference evidence; "
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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1404_MAX_EVIDENCE)


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
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1404_MAX_ASSUMPTIONS)
    alternatives: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1404_MAX_ALTERNATIVES)
    counter_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1404_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1404_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1404_MAX_EVIDENCE)


class InferProteinSubtypeMechanismRequest(FrozenModel):
    """Provisional request bound to the M14-01 hypothesis registry."""

    operation: Literal["infer_protein_subtype_mechanism"] = M1404_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1404_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    hypothesis_registry_result: ArtifactReference
    configuration: MechanismInferenceConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1404_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> InferProteinSubtypeMechanismRequest:
        if self.hypothesis_registry_result.media_type != M1404_M1401_RESULT_MEDIA_TYPE:
            raise ValueError("mechanism request must bind the provisional M14-01 result")
        return self


class ProteinSubtypeMechanismInferenceResult(FrozenModel):
    """Mechanism estimates with counter-evidence and explicit abstention."""

    output_type: Literal["protein_subtype_mechanism_inference"] = (
        "protein_subtype_mechanism_inference"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1404_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: InferProteinSubtypeMechanismRequest
    status: MechanismInferenceStatus
    estimates: tuple[MechanismEstimate, ...] = Field(default=(), max_length=M1404_MAX_ESTIMATES)
    findings: tuple[MechanismFinding, ...] = Field(default=(), max_length=M1404_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M1404_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1404_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeMechanismInferenceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is MechanismInferenceStatus.INFERRED:
            if (
                not self.estimates
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("inferred result requires supported mechanism estimates")
        elif (
            self.estimates
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no estimates and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1404_CONTRACT_VERSION",
    "M1404_EVIDENCE_CLAIM",
    "M1404_GATE",
    "M1404_M1401_RESULT_MEDIA_TYPE",
    "M1404_MAX_ALTERNATIVES",
    "M1404_MAX_ASSUMPTIONS",
    "M1404_MAX_CANONICAL_REQUEST_BYTES",
    "M1404_MAX_CANONICAL_RESULT_BYTES",
    "M1404_MAX_ESTIMATES",
    "M1404_MAX_EVIDENCE",
    "M1404_MAX_FINDINGS",
    "M1404_MODULE_ID",
    "M1404_OPERATION",
    "M1404_OUTPUT_MEDIA_TYPE",
    "M1404_OWNER",
    "M1404_PARENT",
    "M1404_PROVISIONAL_ABI",
    "M1404_SAFETY_CLASS",
    "InferProteinSubtypeMechanismRequest",
    "MechanismEstimate",
    "MechanismEstimateKind",
    "MechanismFinding",
    "MechanismFindingCode",
    "MechanismInferenceConfiguration",
    "MechanismInferenceStatus",
    "ProteinSubtypeMechanismInferenceResult",
]
