"""Provisional M15-01 biological hypothesis registry contracts.

The M15-01 dossier requires versioned hypotheses, competing explanations,
falsification rules, evidence tiers, and prohibited interpretations. The
public registry ABI is not frozen, so all symbols here are provisional
scaffolding pending owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m15_01.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M15-01 dossier slice.
M1501_MODULE_ID: Final = "GLIO-PROTEOGEN-M15-01"
M1501_OPERATION: Final = "register_complex_activity_hypotheses"
M1501_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1501_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m15-01+json"
M1501_PARENT: Final = "complex_activity"
M1501_OWNER: Final = "Data engineering"
M1501_SAFETY_CLASS: Final = "S2"
M1501_GATE: Final = "G0"
M1501_PROVISIONAL_ABI: Final = True
M1501_MAX_HYPOTHESES: Final = 256
M1501_MAX_EXPLANATIONS: Final = 16
M1501_MAX_RULES: Final = 16
M1501_MAX_EVIDENCE_TIERS: Final = 8
M1501_MAX_EVALUATIONS: Final = M1501_MAX_HYPOTHESES
M1501_MAX_FALSIFICATION_EVALUATIONS: Final = M1501_MAX_HYPOTHESES * M1501_MAX_RULES
M1501_MAX_EVIDENCE: Final = 64
M1501_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1501_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1501_EVIDENCE_CLAIM: Final = (
    "Caller-declared M15-01 hypothesis, falsification, and evidence-tier material; "
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
        min_length=1, max_length=M1501_MAX_EVIDENCE
    )


class FalsificationRule(FrozenModel):
    rule_id: Identifier
    criterion: NonEmptyStr
    failure_condition: NonEmptyStr
    required_evidence: tuple[EvidenceReference, ...] = Field(
        min_length=1, max_length=M1501_MAX_EVIDENCE
    )
    prohibited_interpretation: NonEmptyStr


class EvidenceTier(FrozenModel):
    tier: int = Field(ge=1, le=M1501_MAX_EVIDENCE_TIERS)
    label: NonEmptyStr
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1501_MAX_EVIDENCE)


class BiologicalHypothesis(FrozenModel):
    hypothesis_id: Identifier
    version: SemanticVersion
    statement: NonEmptyStr
    mechanism_class: NonEmptyStr
    target_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1501_MAX_HYPOTHESES)
    competing_explanations: tuple[CompetingExplanation, ...] = Field(
        min_length=1, max_length=M1501_MAX_EXPLANATIONS
    )
    falsification_rules: tuple[FalsificationRule, ...] = Field(
        min_length=1, max_length=M1501_MAX_RULES
    )
    evidence_tiers: tuple[EvidenceTier, ...] = Field(
        min_length=1, max_length=M1501_MAX_EVIDENCE_TIERS
    )
    prohibited_interpretations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1501_MAX_EVIDENCE)

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
        min_length=1, max_length=M1501_MAX_HYPOTHESES
    )
    reviewed_by: Identifier
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1501_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1501_MAX_EVIDENCE)


class FalsificationEvaluation(FrozenModel):
    hypothesis_id: Identifier
    rule_id: Identifier
    outcome: FalsificationOutcome
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1501_MAX_EVIDENCE)


class HypothesisFinding(FrozenModel):
    finding_id: Identifier
    code: HypothesisFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1501_MAX_EVIDENCE)


class RegisterComplexActivityHypothesesRequest(FrozenModel):
    """Provisional request for registering a complete hypothesis registry."""

    operation: Literal["register_complex_activity_hypotheses"] = M1501_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1501_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    registry_version: SemanticVersion
    hypotheses: tuple[BiologicalHypothesis, ...] = Field(
        min_length=1, max_length=M1501_MAX_HYPOTHESES
    )
    reviewer_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1501_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> RegisterComplexActivityHypothesesRequest:
        ids = tuple(item.hypothesis_id for item in self.hypotheses)
        if len(ids) != len(set(ids)):
            raise ValueError("request hypothesis ids must be unique")
        return self


class ComplexActivityHypothesisRegistryResult(FrozenModel):
    """Versioned registry with complete evaluations and explicit abstention."""

    output_type: Literal["complex_activity_hypothesis_registry"] = (
        "complex_activity_hypothesis_registry"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1501_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RegisterComplexActivityHypothesesRequest
    status: HypothesisStatus
    registry: HypothesisRegistry | None = None
    evaluations: tuple[HypothesisEvaluation, ...] = Field(
        default=(), max_length=M1501_MAX_EVALUATIONS
    )
    falsification_evaluations: tuple[FalsificationEvaluation, ...] = Field(
        default=(), max_length=M1501_MAX_FALSIFICATION_EVALUATIONS
    )
    findings: tuple[HypothesisFinding, ...] = Field(default=(), max_length=M1501_MAX_EVIDENCE)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex_activity"] = M1501_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1501_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityHypothesisRegistryResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
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
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("registered result requires a supported registry")
        elif (
            self.registry is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no registry and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1501_CONTRACT_VERSION",
    "M1501_EVIDENCE_CLAIM",
    "M1501_GATE",
    "M1501_MAX_CANONICAL_REQUEST_BYTES",
    "M1501_MAX_CANONICAL_RESULT_BYTES",
    "M1501_MAX_EVALUATIONS",
    "M1501_MAX_EVIDENCE",
    "M1501_MAX_EVIDENCE_TIERS",
    "M1501_MAX_EXPLANATIONS",
    "M1501_MAX_FALSIFICATION_EVALUATIONS",
    "M1501_MAX_HYPOTHESES",
    "M1501_MAX_RULES",
    "M1501_MODULE_ID",
    "M1501_OPERATION",
    "M1501_OUTPUT_MEDIA_TYPE",
    "M1501_OWNER",
    "M1501_PARENT",
    "M1501_PROVISIONAL_ABI",
    "M1501_SAFETY_CLASS",
    "BiologicalHypothesis",
    "CompetingExplanation",
    "ComplexActivityHypothesisRegistryResult",
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
    "RegisterComplexActivityHypothesesRequest",
]
