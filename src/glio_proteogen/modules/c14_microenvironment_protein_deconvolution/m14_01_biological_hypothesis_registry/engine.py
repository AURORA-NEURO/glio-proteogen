"""Deterministic, replay-bound M14-01 hypothesis registry runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_01 import (
    M1401_CONTRACT_VERSION,
    M1401_EVIDENCE_CLAIM,
    M1401_PARENT,
    BiologicalHypothesis,
    FalsificationEvaluation,
    FalsificationOutcome,
    HypothesisEvaluation,
    HypothesisEvaluationStatus,
    HypothesisFinding,
    HypothesisFindingCode,
    HypothesisRegistry,
    HypothesisStatus,
    ProteinSubtypeHypothesisRegistryResult,
    RegisterProteinSubtypeHypothesesRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m14_01.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import EvidenceReference as KernelEvidenceReference
from glio_proteogen.kernel.models import Limitation, SupportDecision, SupportStatus

_REQUEST_ADAPTER: Final = TypeAdapter(RegisterProteinSubtypeHypothesesRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeHypothesisRegistryResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED: Final = frozenset({"supported", "always_true", "true", "confirmed"})
_REFUTED: Final = frozenset({"refuted", "always_false", "false"})
_PASSED: Final = frozenset({"passed", "always_pass", "pass", "satisfied"})
_FAILED: Final = frozenset({"failed", "always_fail", "fail", "violated"})


class M1401HypothesisAuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for registry evaluation."""

    def __init__(self) -> None:
        super().__init__(
            "M14-01 requires accepted controls, resolved identity, and granted consent"
        )


class M1401ReplayVerificationError(ValueError):
    """A registry result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-01 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_hypothesis_authorization(candidate: object) -> None:
    """Read seven controls before traversing opaque hypothesis material."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001
        raise M1401HypothesisAuthorizationError from None
    if states != expected:
        raise M1401HypothesisAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_hypothesis_authorization(candidate)
    return candidate


def _evidence(
    request: RegisterProteinSubtypeHypothesesRequest,
) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    source = (
        *request.source_artifacts,
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        *(
            item.reference
            for hypothesis in request.hypotheses
            for tier in hypothesis.evidence_tiers
            for item in tier.evidence
        ),
    )
    return tuple(
        KernelEvidenceReference(reference=artifact, role="evidence", claim=M1401_EVIDENCE_CLAIM)
        for artifact in source[:64]
    )


def _statement_outcome(statement: str) -> HypothesisEvaluationStatus:
    normalized = statement.strip().lower()
    if normalized in _SUPPORTED:
        return HypothesisEvaluationStatus.SUPPORTED
    if normalized in _REFUTED:
        return HypothesisEvaluationStatus.REFUTED
    return HypothesisEvaluationStatus.NOT_EVALUABLE


def _falsification_outcome(failure_condition: str) -> FalsificationOutcome:
    normalized = failure_condition.strip().lower()
    if normalized in _PASSED:
        return FalsificationOutcome.PASSED
    if normalized in _FAILED:
        return FalsificationOutcome.FAILED
    return FalsificationOutcome.NOT_EVALUABLE


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_inputs",
            statement="Source artifacts are immutable references and are never traversed.",
        ),
        Limitation(
            code="competing_explanations_preserved",
            statement="Competing explanations and falsification rules remain in the registry.",
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, all-omics fusion, treatment recommendation, identity "
                "inference, or consent inference is emitted."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="No registry is published until every hypothesis and rule is evaluable.",
            )
        )
    return tuple(values)


class M1401HypothesisEngine:
    """Evaluate explicit caller-declared hypotheses without hidden interpretation."""

    __slots__ = ()

    def register(self, request: object) -> ProteinSubtypeHypothesisRegistryResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: RegisterProteinSubtypeHypothesesRequest,
    ) -> ProteinSubtypeHypothesisRegistryResult:
        request_hash = canonical_request_digest(request)
        evaluations: list[HypothesisEvaluation] = []
        falsification: list[FalsificationEvaluation] = []
        findings: list[HypothesisFinding] = []
        evaluated_hypotheses: list[BiologicalHypothesis] = []
        safe = True
        for hypothesis in request.hypotheses:
            evaluation_status = _statement_outcome(hypothesis.statement)
            rule_outcomes = [
                _falsification_outcome(rule.failure_condition)
                for rule in hypothesis.falsification_rules
            ]
            if evaluation_status is not HypothesisEvaluationStatus.SUPPORTED or any(
                outcome is not FalsificationOutcome.PASSED for outcome in rule_outcomes
            ):
                safe = False
            evaluations.append(
                HypothesisEvaluation(
                    hypothesis_id=hypothesis.hypothesis_id,
                    status=evaluation_status,
                    rationale=(
                        "closed hypothesis statement is supported"
                        if evaluation_status is HypothesisEvaluationStatus.SUPPORTED
                        else "hypothesis statement is refuted or outside the closed vocabulary"
                    ),
                    evidence=hypothesis.evidence,
                )
            )
            if evaluation_status is not HypothesisEvaluationStatus.SUPPORTED:
                findings.append(
                    HypothesisFinding(
                        finding_id=f"finding.{hypothesis.hypothesis_id}",
                        code=(
                            HypothesisFindingCode.FALSIFICATION_NOT_EVALUABLE
                            if evaluation_status is HypothesisEvaluationStatus.NOT_EVALUABLE
                            else HypothesisFindingCode.PROHIBITED_INTERPRETATION
                        ),
                        message="hypothesis cannot be safely registered",
                        evidence=hypothesis.evidence,
                    )
                )
            evaluated_hypotheses.append(
                hypothesis.model_copy(
                    update={
                        "status": HypothesisStatus.SUPPORTED
                        if evaluation_status is HypothesisEvaluationStatus.SUPPORTED
                        else HypothesisStatus.ABSTAINED
                    }
                )
            )
            for rule, outcome in zip(hypothesis.falsification_rules, rule_outcomes, strict=True):
                falsification.append(
                    FalsificationEvaluation(
                        hypothesis_id=hypothesis.hypothesis_id,
                        rule_id=rule.rule_id,
                        outcome=outcome,
                        rationale=(
                            "closed falsification condition passed"
                            if outcome is FalsificationOutcome.PASSED
                            else "falsification condition failed or is not evaluable"
                        ),
                        evidence=rule.required_evidence,
                    )
                )
        supported = safe
        registry_status = HypothesisStatus.SUPPORTED if supported else HypothesisStatus.ABSTAINED
        registry = (
            HypothesisRegistry(
                registry_id=f"registry.{request.request_id}",
                version=request.registry_version,
                hypotheses=tuple(evaluated_hypotheses),
                reviewed_by=request.reviewer_id,
                evidence=_evidence(request),
            )
            if supported
            else None
        )
        payload: dict[str, object] = {
            "output_type": "protein_subtype_hypothesis_registry",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1401_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": registry_status,
            "registry": registry,
            "evaluations": tuple(evaluations),
            "falsification_evaluations": tuple(falsification),
            "findings": tuple(findings),
            "abstention_reason": None
            if supported
            else "At least one hypothesis or falsification rule is not safely evaluable.",
            "parent_target": M1401_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.UNSUPPORTED,
                reason_code="m1401_registry_supported" if supported else "m1401_registry_abstained",
                rationale=(
                    "All hypotheses and falsification rules passed the closed registry gates."
                    if supported
                    else (
                        "Registry publication is withheld until every required condition "
                        "is evaluable."
                    )
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteinSubtypeHypothesisRegistryResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeHypothesisRegistryResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1401ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1401ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1401ReplayVerificationError
        if replay:
            expected = self.register(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1401ReplayVerificationError
        return validated


def register_protein_subtype_hypotheses(
    request: object,
) -> ProteinSubtypeHypothesisRegistryResult:
    """Public provisional M14-01 operation."""

    return M1401HypothesisEngine().register(request)


__all__ = [
    "M1401HypothesisAuthorizationError",
    "M1401HypothesisEngine",
    "M1401ReplayVerificationError",
    "preflight_hypothesis_authorization",
    "register_protein_subtype_hypotheses",
]
