"""Deterministic, fail-closed M15-01 hypothesis registry runtime."""

from __future__ import annotations

# ruff: noqa: TRY003, TRY301
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_01 import (
    M1501_OPERATION,
    BiologicalHypothesis,
    ComplexActivityHypothesisRegistryResult,
    FalsificationEvaluation,
    FalsificationOutcome,
    HypothesisEvaluation,
    HypothesisEvaluationStatus,
    HypothesisFinding,
    HypothesisFindingCode,
    HypothesisRegistry,
    HypothesisStatus,
    RegisterComplexActivityHypothesesRequest,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER = TypeAdapter(RegisterComplexActivityHypothesesRequest)
_RESULT_ADAPTER = TypeAdapter(ComplexActivityHypothesisRegistryResult)
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_PROHIBITED_TOKENS: Final = (
    "kinase",
    "treatment",
    "identity",
    "consent",
    "all-omics",
    "mutation",
    "relabel",
    "erasure",
)


class M1501AuthorizationError(ValueError):
    """Raised when upstream controls do not authorize registry execution."""


class M1501InferenceError(ValueError):
    """Raised when a typed hypothesis request cannot be evaluated safely."""


class M1501ReplayVerificationError(ValueError):
    """Raised when a result digest or deterministic replay does not match."""


def _state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1501AuthorizationError("M15-01 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1501AuthorizationError("M15-01 controls are unavailable")
    return state


def preflight_hypothesis_authorization(request: object) -> None:
    """Check seven upstream controls without traversing arbitrary opaque objects."""

    try:
        if isinstance(request, RegisterComplexActivityHypothesesRequest):
            references = request.context.references
            actual = {
                "approved_configuration": references.approved_configuration.state.value,
                "identity_lineage": references.identity_lineage.state.value,
                "provenance": references.provenance.state.value,
                "consent": references.consent.state.value,
                "quality": references.quality.state.value,
                "support": references.support.state.value,
                "intended_use": references.intended_use.state.value,
            }
            if actual != _EXPECTED_STATES:
                raise M1501AuthorizationError("M15-01 controls do not authorize registration")
            return
        if not isinstance(request, Mapping):
            raise M1501AuthorizationError("M15-01 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1501AuthorizationError("M15-01 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1501AuthorizationError("M15-01 request controls are unavailable")
        for role, expected in _EXPECTED_STATES.items():
            if _state(raw_references.get(role)) != expected:
                raise M1501AuthorizationError("M15-01 controls do not authorize registration")
    except M1501AuthorizationError:
        raise
    except Exception as error:
        raise M1501AuthorizationError("M15-01 controls are unavailable") from error


def _evidence(request: RegisterComplexActivityHypothesesRequest) -> tuple[EvidenceReference, ...]:
    references: list[ArtifactReference] = [*request.source_artifacts]
    for hypothesis in request.hypotheses:
        references.extend(item.reference for item in hypothesis.evidence)
        for explanation in hypothesis.competing_explanations:
            references.extend(item.reference for item in explanation.required_evidence)
        for rule in hypothesis.falsification_rules:
            references.extend(item.reference for item in rule.required_evidence)
        for tier in hypothesis.evidence_tiers:
            references.extend(item.reference for item in tier.evidence)
    unique = {item.digest: item for item in references}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M15-01 hypothesis and falsification evidence.",
        )
        for artifact in unique.values()
    )


def _finding(
    finding_id: str,
    code: HypothesisFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> HypothesisFinding:
    return HypothesisFinding(
        finding_id=finding_id,
        code=code,
        message=message,
        evidence=evidence[:1],
    )


def _hypothesis_status(hypothesis: BiologicalHypothesis) -> HypothesisEvaluationStatus:
    declared_claim = f"{hypothesis.statement} {hypothesis.mechanism_class}".casefold()
    if any(token in declared_claim for token in _PROHIBITED_TOKENS):
        return HypothesisEvaluationStatus.ABSTAINED
    tier_text = " ".join(tier.label for tier in hypothesis.evidence_tiers).casefold()
    if any(token in tier_text for token in ("unsupported", "unknown", "unlocked", "not evaluable")):
        return HypothesisEvaluationStatus.NOT_EVALUABLE
    if hypothesis.status in {HypothesisStatus.REFUTED, HypothesisStatus.CONFLICTED}:
        return HypothesisEvaluationStatus.CONFLICTED
    return HypothesisEvaluationStatus.SUPPORTED


def _rule_outcome(hypothesis: BiologicalHypothesis, rule_id: str) -> FalsificationOutcome:
    rule = next(item for item in hypothesis.falsification_rules if item.rule_id == rule_id)
    text = f"{rule.criterion} {rule.failure_condition}".casefold()
    if any(token in text for token in ("not evaluable", "unsupported", "unknown")):
        return FalsificationOutcome.NOT_EVALUABLE
    if "abstain" in text:
        return FalsificationOutcome.ABSTAINED
    if any(token in text for token in ("fail", "contradict", "absent")):
        return FalsificationOutcome.FAILED
    return FalsificationOutcome.PASSED


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1501_no_kinase_or_treatment",
            statement=(
                "Hypothesis registration does not infer kinase activity or recommend treatment."
            ),
        ),
        Limitation(
            code="m1501_provisional_abi",
            statement=(
                "The M15-01 ABI and registry vocabulary remain provisional pending owner review."
            ),
        ),
        Limitation(
            code="m1501_supported" if supported else "m1501_review_required",
            statement=(
                "All declared hypotheses and falsification rules passed in the support domain."
                if supported
                else "Unsupported, prohibited, conflicted, or failed evidence requires review."
            ),
        ),
    )


class M1501HypothesisRegistry:
    """Stateless deterministic hypothesis and falsification evaluator."""

    def infer(self, request: object) -> ComplexActivityHypothesisRegistryResult:
        preflight_hypothesis_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1501InferenceError from error
        request_digest = sha256_digest(typed.model_dump(mode="json"))
        evidence = _evidence(typed)
        evaluations: list[HypothesisEvaluation] = []
        falsification: list[FalsificationEvaluation] = []
        findings: list[HypothesisFinding] = [
            _finding(
                "finding.provisional-abi",
                HypothesisFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "M15-01 ABI remains provisional pending owner confirmation.",
                evidence,
            )
        ]
        for hypothesis in typed.hypotheses:
            status = _hypothesis_status(hypothesis)
            if status is HypothesisEvaluationStatus.ABSTAINED:
                findings.append(
                    _finding(
                        f"finding.prohibited.{hypothesis.hypothesis_id}",
                        HypothesisFindingCode.PROHIBITED_INTERPRETATION,
                        "A prohibited interpretation appears in the declared hypothesis boundary.",
                        evidence,
                    )
                )
            elif status is HypothesisEvaluationStatus.NOT_EVALUABLE:
                findings.append(
                    _finding(
                        f"finding.tier.{hypothesis.hypothesis_id}",
                        HypothesisFindingCode.EVIDENCE_TIER_NOT_LOCKED,
                        "The declared evidence tier is not locked or supported.",
                        evidence,
                    )
                )
            elif status is HypothesisEvaluationStatus.CONFLICTED:
                findings.append(
                    _finding(
                        f"finding.conflict.{hypothesis.hypothesis_id}",
                        HypothesisFindingCode.MISSING_COMPETING_EXPLANATION,
                        "The hypothesis is declared conflicted and cannot be promoted.",
                        evidence,
                    )
                )
            evaluations.append(
                HypothesisEvaluation(
                    hypothesis_id=hypothesis.hypothesis_id,
                    status=status,
                    rationale=(
                        "Competing explanations and declared evidence support the hypothesis."
                        if status is HypothesisEvaluationStatus.SUPPORTED
                        else "The hypothesis is outside the safely promotable support domain."
                    ),
                    evidence=evidence[:1],
                )
            )
            for rule in hypothesis.falsification_rules:
                outcome = _rule_outcome(hypothesis, rule.rule_id)
                if outcome is not FalsificationOutcome.PASSED:
                    findings.append(
                        _finding(
                            f"finding.falsification.{hypothesis.hypothesis_id}.{rule.rule_id}",
                            HypothesisFindingCode.FALSIFICATION_NOT_EVALUABLE,
                            "A falsification rule did not pass safely.",
                            evidence,
                        )
                    )
                falsification.append(
                    FalsificationEvaluation(
                        hypothesis_id=hypothesis.hypothesis_id,
                        rule_id=rule.rule_id,
                        outcome=outcome,
                        rationale=(
                            "Declared falsification condition is not triggered."
                            if outcome is FalsificationOutcome.PASSED
                            else "Declared falsification condition blocks promotion."
                        ),
                        evidence=evidence[:1],
                    )
                )
        supported = all(
            item.status is HypothesisEvaluationStatus.SUPPORTED for item in evaluations
        ) and all(item.outcome is FalsificationOutcome.PASSED for item in falsification)
        registry = None
        if supported:
            registry = HypothesisRegistry(
                registry_id=f"registry.{typed.registry_version}",
                version=typed.registry_version,
                hypotheses=tuple(
                    item.model_copy(update={"status": HypothesisStatus.SUPPORTED})
                    for item in typed.hypotheses
                ),
                reviewed_by=typed.reviewer_id,
                evidence=evidence[:1],
            )
        payload: dict[str, Any] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": HypothesisStatus.SUPPORTED if supported else HypothesisStatus.ABSTAINED,
            "registry": registry,
            "evaluations": tuple(evaluations),
            "falsification_evaluations": tuple(falsification),
            "findings": tuple(findings),
            "abstention_reason": None
            if supported
            else "One or more hypotheses or falsification rules are not safely promotable.",
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1501_supported" if supported else "m1501_review_required",
                rationale=(
                    "All hypotheses and falsification rules passed."
                    if supported
                    else "Promotion is blocked pending evidence or human review."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ComplexActivityHypothesisRegistryResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1501InferenceError from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityHypothesisRegistryResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1501ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1501ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1501ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1501ReplayVerificationError
        return validated


def register_complex_activity_hypotheses(
    request: object,
) -> ComplexActivityHypothesisRegistryResult:
    """Public provisional M15-01 operation."""

    return M1501HypothesisRegistry().infer(request)


__all__ = [
    "M1501_OPERATION",
    "M1501AuthorizationError",
    "M1501HypothesisRegistry",
    "M1501InferenceError",
    "M1501ReplayVerificationError",
    "preflight_hypothesis_authorization",
    "register_complex_activity_hypotheses",
]
