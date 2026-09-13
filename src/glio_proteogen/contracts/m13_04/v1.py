"""Provisional M13-04 network/state/mechanism inference contracts.

The M13-04 dossier requires a mechanism posterior or state estimate with
explicit assumptions, alternatives, counter-evidence, typed uncertainty, and
safe abstention.  The public ABI and handoff details are not frozen; all
symbols are provisional pending Platform engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m13_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M13-04 dossier slice.
M1304_MODULE_ID: Final = "GLIO-PROTEOGEN-M13-04"
M1304_OPERATION: Final = "infer_proteotype_mechanism"
M1304_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1304_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m11-04+json"
M1304_M1301_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m11-01+json"
M1304_PARENT: Final = "proteotype"
M1304_OWNER: Final = "Platform engineering"
M1304_SAFETY_CLASS: Final = "S2"
M1304_GATE: Final = "G2"
M1304_PROVISIONAL_ABI: Final = True
M1304_MAX_ESTIMATES: Final = 512
M1304_MAX_ASSUMPTIONS: Final = 64
M1304_MAX_ALTERNATIVES: Final = 64
M1304_MAX_EVIDENCE: Final = 64
M1304_MAX_FINDINGS: Final = 64
M1304_MAX_OBSERVATIONS: Final = 512
M1304_MAX_RELATIONS: Final = 1_024
M1304_DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
M1304_MAX_BOOTSTRAP_REPLICATES: Final = 256
M1304_GLIOMA_MODEL_FAMILY: Final = "glioma-proteotype-mechanism-evidence-graph/1.0.0"
M1304_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1304_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1304_EVIDENCE_CLAIM: Final = (
    "Caller-declared M13-01 hypothesis and M13-04 mechanism-inference evidence; "
    "issuer authority is not authenticated."
)
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class MechanismEstimateKind(StrEnum):
    POSTERIOR = "posterior"
    STATE = "state"


class MechanismInferenceStatus(StrEnum):
    INFERRED = "inferred"
    ABSTAINED = "abstained"


class MechanismObservationState(StrEnum):
    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class MechanismRelationKind(StrEnum):
    ACTIVATES = "activates"
    INHIBITS = "inhibits"
    COUPLES = "couples"


class MechanismObservation(FrozenModel):
    """Typed glioma proteotype evidence with explicit non-observation states."""

    observation_id: Identifier
    mechanism_id: Identifier
    label: NonEmptyStr
    standardized_effect: FiniteFloat | None = None
    standard_error: FiniteFloat | None = Field(default=None, gt=0.0)
    quality_weight: FiniteFloat = Field(default=1.0, ge=0.0, le=1.0)
    state: MechanismObservationState = MechanismObservationState.OBSERVED
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1304_MAX_EVIDENCE)

    @model_validator(mode="after")
    def observation_shape_is_closed(self) -> MechanismObservation:
        measured = self.standardized_effect is not None or self.standard_error is not None
        if self.state in {
            MechanismObservationState.OBSERVED,
            MechanismObservationState.LEFT_CENSORED,
        } and (self.standardized_effect is None or self.standard_error is None):
            raise ValueError("observed or censored mechanism evidence requires effect and error")
        if (
            self.state
            in {
                MechanismObservationState.MISSING,
                MechanismObservationState.UNSUPPORTED,
            }
            and measured
        ):
            raise ValueError("missing or unsupported mechanism evidence cannot carry a value")
        return self


class MechanismRelation(FrozenModel):
    relation_id: Identifier
    source_mechanism_id: Identifier
    target_mechanism_id: Identifier
    kind: MechanismRelationKind
    weight: FiniteFloat = Field(default=1.0, ge=-1.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1304_MAX_EVIDENCE)

    @model_validator(mode="after")
    def relation_is_closed(self) -> MechanismRelation:
        if self.source_mechanism_id == self.target_mechanism_id:
            raise ValueError("mechanism relation cannot be a self-loop")
        return self


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
    model_family: NonEmptyStr | None = None
    bootstrap_replicates: int = Field(
        default=M1304_DEFAULT_BOOTSTRAP_REPLICATES,
        ge=16,
        le=M1304_MAX_BOOTSTRAP_REPLICATES,
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1304_MAX_EVIDENCE)


class MechanismEstimate(FrozenModel):
    """Posterior or state estimate with explicit counter-evidence."""

    estimate_id: Identifier
    mechanism_id: Identifier
    label: NonEmptyStr
    kind: MechanismEstimateKind
    posterior_probability: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)
    lower_bound: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)
    upper_bound: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)
    state_value: NonEmptyStr | None = None
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1304_MAX_ASSUMPTIONS)
    alternatives: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1304_MAX_ALTERNATIVES)
    counter_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1304_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1304_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1304_MAX_EVIDENCE)


class InferProteotypeMechanismRequest(FrozenModel):
    """Provisional request bound to the M13-01 hypothesis registry."""

    operation: Literal["infer_proteotype_mechanism"] = M1304_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1304_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    hypothesis_registry_result: ArtifactReference
    configuration: MechanismInferenceConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1304_MAX_EVIDENCE
    )
    typed_observations: tuple[MechanismObservation, ...] = Field(
        default=(), max_length=M1304_MAX_OBSERVATIONS
    )
    typed_relations: tuple[MechanismRelation, ...] = Field(
        default=(), max_length=M1304_MAX_RELATIONS
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> InferProteotypeMechanismRequest:
        if self.hypothesis_registry_result.media_type != M1304_M1301_RESULT_MEDIA_TYPE:
            raise ValueError("mechanism request must bind the provisional M13-01 result")
        observation_ids = tuple(item.observation_id for item in self.typed_observations)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("mechanism observation ids must be unique")
        relation_ids = tuple(item.relation_id for item in self.typed_relations)
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("mechanism relation ids must be unique")
        known = {item.mechanism_id for item in self.typed_observations}
        for relation in self.typed_relations:
            if (
                relation.source_mechanism_id not in known
                or relation.target_mechanism_id not in known
            ):
                raise ValueError("mechanism relation references an unknown mechanism")
        return self


class ProteotypeMechanismInferenceResult(FrozenModel):
    """Mechanism estimates with counter-evidence and explicit abstention."""

    output_type: Literal["proteotype_mechanism_inference"] = "proteotype_mechanism_inference"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1304_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: InferProteotypeMechanismRequest
    status: MechanismInferenceStatus
    estimates: tuple[MechanismEstimate, ...] = Field(default=(), max_length=M1304_MAX_ESTIMATES)
    findings: tuple[MechanismFinding, ...] = Field(default=(), max_length=M1304_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1304_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1304_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False
    typed_model: bool = False
    model_profile: NonEmptyStr | None = None
    solver_iterations: int = Field(default=0, ge=0)
    solver_objective: FiniteFloat | None = Field(default=None, ge=0.0)
    converged: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeMechanismInferenceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        estimate_ids = tuple(item.estimate_id for item in self.estimates)
        if len(estimate_ids) != len(set(estimate_ids)):
            raise ValueError("estimate ids must be unique")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding ids must be unique")
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
        if self.status is MechanismInferenceStatus.ABSTAINED and not self.human_review_required:
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
            "Closed mechanism evidence and calibration references are present; population "
            "coverage is not inferred from a single request."
            if supported
            else "Mechanism evidence, quality, or upstream support was not safely evaluable."
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
            "Assumptions, alternatives, counter-evidence, and sensitivity are retained.",
            "Unsupported or missing evidence is never converted into a negative mechanism.",
        ),
    )


def expected_provenance(
    request: InferProteotypeMechanismRequest,
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
        module_id=M1304_MODULE_ID,
        module_version=M1304_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.hypothesis_registry_result.digest,
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
    "M1304_CONTRACT_VERSION",
    "M1304_DEFAULT_BOOTSTRAP_REPLICATES",
    "M1304_EVIDENCE_CLAIM",
    "M1304_GATE",
    "M1304_GLIOMA_MODEL_FAMILY",
    "M1304_M1301_RESULT_MEDIA_TYPE",
    "M1304_MAX_ALTERNATIVES",
    "M1304_MAX_ASSUMPTIONS",
    "M1304_MAX_BOOTSTRAP_REPLICATES",
    "M1304_MAX_CANONICAL_REQUEST_BYTES",
    "M1304_MAX_CANONICAL_RESULT_BYTES",
    "M1304_MAX_ESTIMATES",
    "M1304_MAX_EVIDENCE",
    "M1304_MAX_FINDINGS",
    "M1304_MAX_OBSERVATIONS",
    "M1304_MAX_RELATIONS",
    "M1304_MODULE_ID",
    "M1304_OPERATION",
    "M1304_OUTPUT_MEDIA_TYPE",
    "M1304_OWNER",
    "M1304_PARENT",
    "M1304_PROVISIONAL_ABI",
    "M1304_SAFETY_CLASS",
    "InferProteotypeMechanismRequest",
    "MechanismEstimate",
    "MechanismEstimateKind",
    "MechanismFinding",
    "MechanismFindingCode",
    "MechanismInferenceConfiguration",
    "MechanismInferenceStatus",
    "MechanismObservation",
    "MechanismObservationState",
    "MechanismRelation",
    "MechanismRelationKind",
    "ProteotypeMechanismInferenceResult",
    "expected_provenance",
    "expected_uncertainty",
]
