"""Provisional M10-05 mechanism and constraint integrator contracts.

The M10-05 dossier requires typed biological and assay constraints, explicit
hard/soft semantics, satisfaction reporting, and ablation evidence.  It does
not freeze the operation, request/result names, schema inventory, media type,
or the M10-04 handoff ABI.  Every symbol here is reviewable scaffolding and is
explicitly provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m10_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M10-05 dossier slice.
M1005_MODULE_ID: Final = "GLIO-PROTEOGEN-M10-05"
M1005_OPERATION: Final = "integrate_protein_rna_constraints"
M1005_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1005_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-05+json"
M1005_M1002_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-02+json"
M1005_M1004_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m10-04+json"
M1005_PARENT: Final = "protein_rna_discordance"
M1005_OWNER: Final = "Clinical science"
M1005_SAFETY_CLASS: Final = "S2"
M1005_GATE: Final = "G2"
M1005_PROVISIONAL_ABI: Final = True
M1005_MAX_FEATURES: Final = 2_048
M1005_MAX_CONSTRAINTS: Final = 512
M1005_MAX_EVALUATIONS: Final = M1005_MAX_CONSTRAINTS
M1005_MAX_ABLATIONS: Final = M1005_MAX_CONSTRAINTS
M1005_MAX_EVIDENCE: Final = 64
M1005_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1005_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
_M1005_ABLATION_TOLERANCE: Final = 1e-12
M1005_EVIDENCE_CLAIM: Final = (
    "Caller-declared M10-05 mechanism and constraint evidence; issuer authority "
    "is not authenticated."
)


class ConstraintKind(StrEnum):
    BIOLOGICAL_PRIOR = "biological_prior"
    ONTOLOGY = "ontology"
    GRAPH = "graph"
    TOPOLOGY = "topology"
    CONSERVATION = "conservation"
    CHEMISTRY = "chemistry"
    ASSAY_PHYSICS = "assay_physics"
    DISEASE = "disease"


class ConstraintHardness(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class ConstraintEvaluationOutcome(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class ConstraintIntegrationStatus(StrEnum):
    INTEGRATED = "integrated"
    ABSTAINED = "abstained"


class MechanismConstraint(FrozenModel):
    constraint_id: Identifier
    kind: ConstraintKind
    hardness: ConstraintHardness
    expression: NonEmptyStr
    feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1005_MAX_FEATURES)
    weight: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1005_MAX_EVIDENCE)

    @model_validator(mode="after")
    def constraint_shape_is_closed(self) -> MechanismConstraint:
        if self.hardness is ConstraintHardness.HARD and self.weight is not None:
            raise ValueError("hard constraints cannot carry a soft weight")
        if self.hardness is ConstraintHardness.SOFT and self.weight is None:
            raise ValueError("soft constraints require an explicit weight")
        if len(self.feature_ids) != len(set(self.feature_ids)):
            raise ValueError("constraint feature ids must be unique")
        return self


class MechanismConstraintSet(FrozenModel):
    set_id: Identifier
    version: SemanticVersion
    constraints: tuple[MechanismConstraint, ...] = Field(
        min_length=1, max_length=M1005_MAX_CONSTRAINTS
    )
    reviewed_by: Identifier
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1005_MAX_EVIDENCE)

    @model_validator(mode="after")
    def constraint_set_is_closed(self) -> MechanismConstraintSet:
        ids = tuple(item.constraint_id for item in self.constraints)
        if len(ids) != len(set(ids)):
            raise ValueError("constraint ids must be unique")
        return self


class ConstraintEvaluation(FrozenModel):
    constraint_id: Identifier
    outcome: ConstraintEvaluationOutcome
    residual: float | None = None
    effect_size: float | None = None
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1005_MAX_EVIDENCE)


class ConstraintAblation(FrozenModel):
    constraint_id: Identifier
    with_constraint_effect: float
    without_constraint_effect: float
    effect_delta: float
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1005_MAX_EVIDENCE)

    @model_validator(mode="after")
    def effect_delta_is_canonical(self) -> ConstraintAblation:
        expected = self.with_constraint_effect - self.without_constraint_effect
        if abs(self.effect_delta - expected) > _M1005_ABLATION_TOLERANCE:
            raise ValueError("ablation effect delta must equal with-minus-without effect")
        return self


class ConstraintAwareEstimate(FrozenModel):
    estimate_label: NonEmptyStr
    score: float = Field(ge=0.0, le=1.0)
    lower_bound: float | None = None
    upper_bound: float | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1005_MAX_EVIDENCE)

    @model_validator(mode="after")
    def estimate_bounds_are_closed(self) -> ConstraintAwareEstimate:
        if self.lower_bound is not None and self.upper_bound is not None:
            if self.lower_bound > self.upper_bound:
                raise ValueError("estimate bounds are not ordered")
            if not self.lower_bound <= self.score <= self.upper_bound:
                raise ValueError("estimate score must lie within its bounds")
        return self


class IntegrateProteinRnaConstraintsRequest(FrozenModel):
    """Provisional request ABI bound to representation and advanced estimates."""

    operation: Literal["integrate_protein_rna_constraints"] = M1005_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1005_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    representation_result: ArtifactReference
    constraint_set: MechanismConstraintSet
    advanced_estimator_result: ArtifactReference
    feature_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1005_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> IntegrateProteinRnaConstraintsRequest:
        if self.representation_result.media_type != M1005_M1002_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M10-02 representation result")
        if self.advanced_estimator_result.media_type != M1005_M1004_RESULT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M10-04 estimator result")
        artifacts = (
            self.representation_result,
            self.advanced_estimator_result,
            *self.feature_artifacts,
        )
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type) for item in artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("input artifact references must be unique")
        return self


class ProteinRnaConstraintIntegrationResult(FrozenModel):
    """Constraint-aware result with hard/soft safety and explicit abstention."""

    output_type: Literal["protein_rna_constraint_integration"] = (
        "protein_rna_constraint_integration"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1005_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: IntegrateProteinRnaConstraintsRequest
    status: ConstraintIntegrationStatus
    estimates: tuple[ConstraintAwareEstimate, ...] = Field(
        default=(), max_length=M1005_MAX_FEATURES
    )
    evaluations: tuple[ConstraintEvaluation, ...] = Field(
        default=(), max_length=M1005_MAX_EVALUATIONS
    )
    ablations: tuple[ConstraintAblation, ...] = Field(default=(), max_length=M1005_MAX_ABLATIONS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1005_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1005_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaConstraintIntegrationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("every result requires evidence references with the evidence role")
        expected_ids = {item.constraint_id for item in self.request.constraint_set.constraints}
        evaluation_ids = tuple(item.constraint_id for item in self.evaluations)
        if set(evaluation_ids) != expected_ids or len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("every constraint must have exactly one evaluation")
        soft_ids = {
            item.constraint_id
            for item in self.request.constraint_set.constraints
            if item.hardness is ConstraintHardness.SOFT
        }
        ablation_ids = tuple(item.constraint_id for item in self.ablations)
        if set(ablation_ids) != soft_ids or len(ablation_ids) != len(set(ablation_ids)):
            raise ValueError("every soft constraint must have exactly one ablation")
        hard_violations = {
            item.constraint_id
            for item in self.evaluations
            if item.outcome is ConstraintEvaluationOutcome.VIOLATED
            and next(
                constraint.hardness
                for constraint in self.request.constraint_set.constraints
                if constraint.constraint_id == item.constraint_id
            )
            is ConstraintHardness.HARD
        }
        not_evaluable = {
            item.constraint_id
            for item in self.evaluations
            if item.outcome
            in {
                ConstraintEvaluationOutcome.NOT_EVALUABLE,
                ConstraintEvaluationOutcome.ABSTAINED,
            }
        }
        if self.status is ConstraintIntegrationStatus.INTEGRATED:
            if (
                not self.estimates
                or self.abstention_reason is not None
                or hard_violations
                or not_evaluable
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("integrated result requires estimates and no hard violation")
        elif (
            self.estimates
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no estimates and safe status")
        if self.status is ConstraintIntegrationStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstention requires human review acknowledgement")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, integrated: bool) -> UncertaintyProfile:
    """Return seven explicit uncertainty dimensions for every outcome."""

    state = EstimateState.ESTIMATED if integrated else EstimateState.NOT_ESTIMABLE
    rationale = (
        "Constraint residual and ablation uncertainty is reported from the locked input "
        "envelope; transport and population calibration remain outside this module."
        if integrated
        else "The constraint set is not safely evaluable, so no uncertainty is estimated."
    )
    estimate = UncertaintyEstimate(
        state=state,
        probability=0.9 if integrated else None,
        rationale=rationale,
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
            "Soft-constraint ablations are explicit and cannot override hard constraints.",
            "Unsupported or missing evidence is never converted into a negative finding.",
        ),
    )


def expected_provenance(
    request: IntegrateProteinRnaConstraintsRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project all seven controls and immutable constraint inputs in governed order."""

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
    inputs = (
        request_digest,
        request.representation_result.digest,
        request.advanced_estimator_result.digest,
        *(artifact.digest for artifact in request.feature_artifacts),
        *(item.evidence_digest for item in decisions),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1005_MODULE_ID,
        module_version=M1005_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=inputs,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M1005_CONTRACT_VERSION",
    "M1005_EVIDENCE_CLAIM",
    "M1005_GATE",
    "M1005_M1002_RESULT_MEDIA_TYPE",
    "M1005_M1004_RESULT_MEDIA_TYPE",
    "M1005_MAX_ABLATIONS",
    "M1005_MAX_CANONICAL_REQUEST_BYTES",
    "M1005_MAX_CANONICAL_RESULT_BYTES",
    "M1005_MAX_CONSTRAINTS",
    "M1005_MAX_EVALUATIONS",
    "M1005_MAX_EVIDENCE",
    "M1005_MAX_FEATURES",
    "M1005_MODULE_ID",
    "M1005_OPERATION",
    "M1005_OUTPUT_MEDIA_TYPE",
    "M1005_OWNER",
    "M1005_PARENT",
    "M1005_PROVISIONAL_ABI",
    "M1005_SAFETY_CLASS",
    "ConstraintAblation",
    "ConstraintAwareEstimate",
    "ConstraintEvaluation",
    "ConstraintEvaluationOutcome",
    "ConstraintHardness",
    "ConstraintIntegrationStatus",
    "ConstraintKind",
    "IntegrateProteinRnaConstraintsRequest",
    "MechanismConstraint",
    "MechanismConstraintSet",
    "ProteinRnaConstraintIntegrationResult",
    "expected_provenance",
    "expected_uncertainty",
]
