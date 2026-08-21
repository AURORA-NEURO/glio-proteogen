"""Provisional M14-01 biological hypothesis registry contracts.

The M14-01 dossier requires versioned hypotheses, competing explanations,
falsification rules, evidence tiers, and prohibited interpretations.  It does
not freeze the public operation, registry representation, or media type, so
the ABI below is intentionally provisional pending Clinical science owner
confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m14_01.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M14-01 dossier slice.
M1401_MODULE_ID: Final = "GLIO-PROTEOGEN-M14-01"
M1401_OPERATION: Final = "register_protein_subtype_hypotheses"
M1401_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1401_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m11-01+json"
M1401_PARENT: Final = "protein_subtype"
M1401_OWNER: Final = "Clinical science"
M1401_SAFETY_CLASS: Final = "S2"
M1401_GATE: Final = "G0"
M1401_PROVISIONAL_ABI: Final = True
M1401_MAX_HYPOTHESES: Final = 256
M1401_MAX_EXPLANATIONS: Final = 16
M1401_MAX_RULES: Final = 16
M1401_MAX_EVIDENCE_TIERS: Final = 8
M1401_MAX_EVALUATIONS: Final = M1401_MAX_HYPOTHESES
M1401_MAX_FALSIFICATION_EVALUATIONS: Final = M1401_MAX_HYPOTHESES * M1401_MAX_RULES
M1401_MAX_EVIDENCE: Final = 64
M1401_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1401_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1401_EVIDENCE_CLAIM: Final = (
    "Caller-declared M14-01 hypothesis, falsification, and evidence-tier material; "
    "issuer authority is not authenticated."
)


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    CONFLICTED = "conflicted"
    ABSTAINED = "abstained"


class HypothesisEvaluationStatus(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    CONFLICTED = "conflicted"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class FalsificationOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"
    ABSTAINED = "abstained"


class HypothesisFindingCode(StrEnum):
    MISSING_COMPETING_EXPLANATION = "missing_competing_explanation"
    FALSIFICATION_NOT_EVALUABLE = "falsification_not_evaluable"
    EVIDENCE_TIER_NOT_LOCKED = "evidence_tier_not_locked"
    PROHIBITED_INTERPRETATION = "prohibited_interpretation"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class CompetingExplanation(FrozenModel):
    explanation_id: Identifier
    statement: NonEmptyStr
    distinction: NonEmptyStr
    required_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1401_MAX_EVIDENCE
    )


class FalsificationRule(FrozenModel):
    rule_id: Identifier
    criterion: NonEmptyStr
    failure_condition: NonEmptyStr
    required_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1401_MAX_EVIDENCE
    )
    prohibited_interpretation: NonEmptyStr


class EvidenceTier(FrozenModel):
    tier: int = Field(ge=1, le=M1401_MAX_EVIDENCE_TIERS)
    label: NonEmptyStr
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1401_MAX_EVIDENCE)


class BiologicalHypothesis(FrozenModel):
    hypothesis_id: Identifier
    version: SemanticVersion
    statement: NonEmptyStr
    mechanism_class: NonEmptyStr
    target_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1401_MAX_HYPOTHESES)
    competing_explanations: tuple[CompetingExplanation, ...] = Field(
        min_length=1, max_length=M1401_MAX_EXPLANATIONS
    )
    falsification_rules: tuple[FalsificationRule, ...] = Field(
        min_length=1, max_length=M1401_MAX_RULES
    )
    evidence_tiers: tuple[EvidenceTier, ...] = Field(
        min_length=1, max_length=M1401_MAX_EVIDENCE_TIERS
    )
    prohibited_interpretations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1401_MAX_EVIDENCE)

    @model_validator(mode="after")
    def nested_ids_are_unique(self) -> BiologicalHypothesis:
        explanation_ids = tuple(item.explanation_id for item in self.competing_explanations)
        rule_ids = tuple(item.rule_id for item in self.falsification_rules)
        tiers = tuple(item.tier for item in self.evidence_tiers)
        if len(explanation_ids) != len(set(explanation_ids)):
            raise ValueError("competing explanation ids must be unique")
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("falsification rule ids must be unique")
        if len(tiers) != len(set(tiers)):
            raise ValueError("evidence tiers must be unique")
        return self


class HypothesisRegistry(FrozenModel):
    registry_id: Identifier
    version: SemanticVersion
    hypotheses: tuple[BiologicalHypothesis, ...] = Field(
        min_length=1, max_length=M1401_MAX_HYPOTHESES
    )
    reviewed_by: Identifier
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1401_MAX_EVIDENCE)

    @model_validator(mode="after")
    def hypothesis_ids_are_unique(self) -> HypothesisRegistry:
        ids = tuple(item.hypothesis_id for item in self.hypotheses)
        if len(ids) != len(set(ids)):
            raise ValueError("hypothesis ids must be unique")
        return self


class HypothesisEvaluation(FrozenModel):
    hypothesis_id: Identifier
    status: HypothesisEvaluationStatus
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1401_MAX_EVIDENCE)


class FalsificationEvaluation(FrozenModel):
    hypothesis_id: Identifier
    rule_id: Identifier
    outcome: FalsificationOutcome
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1401_MAX_EVIDENCE)


class HypothesisFinding(FrozenModel):
    finding_id: Identifier
    code: HypothesisFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1401_MAX_EVIDENCE)


class RegisterProteinSubtypeHypothesesRequest(FrozenModel):
    """Provisional request for registering a complete hypothesis registry."""

    operation: Literal["register_protein_subtype_hypotheses"] = M1401_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1401_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    registry_version: SemanticVersion
    hypotheses: tuple[BiologicalHypothesis, ...] = Field(
        min_length=1, max_length=M1401_MAX_HYPOTHESES
    )
    reviewer_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1401_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> RegisterProteinSubtypeHypothesesRequest:
        ids = tuple(item.hypothesis_id for item in self.hypotheses)
        if len(ids) != len(set(ids)):
            raise ValueError("request hypothesis ids must be unique")
        return self


class ProteinSubtypeHypothesisRegistryResult(FrozenModel):
    """Versioned registry with complete evaluations and explicit abstention."""

    output_type: Literal["protein_subtype_hypothesis_registry"] = (
        "protein_subtype_hypothesis_registry"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1401_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RegisterProteinSubtypeHypothesesRequest
    status: HypothesisStatus
    registry: HypothesisRegistry | None = None
    evaluations: tuple[HypothesisEvaluation, ...] = Field(
        default=(), max_length=M1401_MAX_EVALUATIONS
    )
    falsification_evaluations: tuple[FalsificationEvaluation, ...] = Field(
        default=(), max_length=M1401_MAX_FALSIFICATION_EVALUATIONS
    )
    findings: tuple[HypothesisFinding, ...] = Field(default=(), max_length=M1401_MAX_EVIDENCE)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_subtype"] = M1401_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1401_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeHypothesisRegistryResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("every result requires evidence references with the evidence role")
        hypothesis_ids = {item.hypothesis_id for item in self.request.hypotheses}
        evaluation_ids = tuple(item.hypothesis_id for item in self.evaluations)
        if set(evaluation_ids) != hypothesis_ids or len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("every hypothesis must have exactly one evaluation")
        expected_rules = {
            (hypothesis.hypothesis_id, rule.rule_id)
            for hypothesis in self.request.hypotheses
            for rule in hypothesis.falsification_rules
        }
        actual_rules = tuple(
            (item.hypothesis_id, item.rule_id) for item in self.falsification_evaluations
        )
        if set(actual_rules) != expected_rules or len(actual_rules) != len(set(actual_rules)):
            raise ValueError("every falsification rule must have exactly one evaluation")
        if self.status is not HypothesisStatus.ABSTAINED:
            if (
                self.registry is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
            ):
                raise ValueError("registered result requires a review-only registry")
        elif (
            self.registry is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no registry and safe status")
        if self.status is HypothesisStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstention requires human review acknowledgement")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, supported: bool) -> UncertaintyProfile:
    """Return explicit seven-axis uncertainty for supported and abstained paths."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "Registry evidence tiers and falsification outcomes are explicit; no population "
            "calibration claim is made."
            if supported
            else "A hypothesis or falsification rule is not safely evaluable."
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
            "Competing explanations and falsification rules remain visible.",
            "Unsupported or missing evidence is never converted into a negative finding.",
        ),
    )


def expected_provenance(
    request: RegisterProteinSubtypeHypothesesRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Project the seven caller controls and opaque source artifacts."""

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
        module_id=M1401_MODULE_ID,
        module_version=M1401_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
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
    "M1401_CONTRACT_VERSION",
    "M1401_EVIDENCE_CLAIM",
    "M1401_GATE",
    "M1401_MAX_CANONICAL_REQUEST_BYTES",
    "M1401_MAX_CANONICAL_RESULT_BYTES",
    "M1401_MAX_EVIDENCE",
    "M1401_MAX_EVIDENCE_TIERS",
    "M1401_MAX_EXPLANATIONS",
    "M1401_MAX_FALSIFICATION_EVALUATIONS",
    "M1401_MAX_HYPOTHESES",
    "M1401_MAX_RULES",
    "M1401_MODULE_ID",
    "M1401_OPERATION",
    "M1401_OUTPUT_MEDIA_TYPE",
    "M1401_OWNER",
    "M1401_PARENT",
    "M1401_PROVISIONAL_ABI",
    "M1401_SAFETY_CLASS",
    "BiologicalHypothesis",
    "CompetingExplanation",
    "EvidenceTier",
    "FalsificationEvaluation",
    "FalsificationOutcome",
    "FalsificationRule",
    "HypothesisEvaluation",
    "HypothesisEvaluationStatus",
    "HypothesisFinding",
    "HypothesisFindingCode",
    "HypothesisRegistry",
    "HypothesisStatus",
    "ProteinSubtypeHypothesisRegistryResult",
    "RegisterProteinSubtypeHypothesesRequest",
    "expected_provenance",
    "expected_uncertainty",
]
