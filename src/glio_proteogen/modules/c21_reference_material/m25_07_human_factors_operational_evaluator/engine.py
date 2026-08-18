"""Deterministic caller-declared M25-07 operational runtime.

The engine evaluates only typed human-factors and operational declarations. It
does not inspect M25-06 scientific content, infer identity or consent, run a
model, or convert an unavailable fallback into a negative conclusion.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_07 import (
    M2507_CONTRACT_VERSION,
    M2507_MODULE_ID,
    EvaluateProteotypeHumanFactorsRequest,
    EvaluationStatus,
    HumanFactorsOperationalReport,
    OperationalFinding,
    OperationalFindingCode,
    OperationalStatus,
    ProteotypeHumanFactorsResult,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteotypeHumanFactorsRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M25-07 evaluation requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M25-06 challenge result is caller-declared; issuer authority and scientific "
            "payload content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="operational_metadata_only",
        statement=(
            "The evaluator compares caller-declared human-factors and operational measurements; "
            "it does not observe reviewers, operate infrastructure, or certify deployment safety."
        ),
    ),
    Limitation(
        code="fallback_not_treatment",
        statement=(
            "Fallback paths are operational review declarations and do not provide identity, "
            "diagnosis, treatment, or clinical eligibility conclusions."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "KINOPHOS kinase ownership, generic all-omics fusion, treatment recommendation, "
            "identity inference, and unsupported-to-negative conversion are outside this module."
        ),
    ),
)


class M2507AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize evaluation."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2507ReplayError(ValueError):
    """Raised when an immutable result fails canonical replay."""

    def __init__(self, message: str = "M25-07 replay verification failed") -> None:
        super().__init__(message)


class M2507HumanFactorsEngine:
    """Build and replay one deterministic operational evaluation."""

    __slots__ = ()

    def generate(self, request: object) -> ProteotypeHumanFactorsResult:
        preflight_m2507_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        report = None if findings else _report(canonical)
        status = EvaluationStatus.EVALUATED if report is not None else EvaluationStatus.ABSTAINED
        payload: dict[str, Any] = {
            "output_type": "proteotype_human_factors_operational",
            "result_id": result_identifier(canonical, status.value),
            "result_version": M2507_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "report": report,
            "findings": findings,
            "abstention_reason": None
            if report is not None
            else "Operational evaluation was not safely evaluable under the declared controls.",
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": _support(completed=report is not None),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        provisional = ProteotypeHumanFactorsResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteotypeHumanFactorsResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(self, result: ProteotypeHumanFactorsResult) -> ProteotypeHumanFactorsResult:
        try:
            replayed = ProteotypeHumanFactorsResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.generate(replayed.request)
        except Exception as error:
            raise M2507ReplayError from error
        if replayed.request_digest != canonical_request_digest(replayed.request):
            raise M2507ReplayError
        if replayed.result_id != result_identifier(replayed.request, replayed.status.value):
            raise M2507ReplayError
        if replayed.result_digest != result_payload_digest(replayed):
            raise M2507ReplayError
        if canonical_json_bytes(expected) != canonical_json_bytes(replayed):
            raise M2507ReplayError("M25-07 deterministic replay output mismatch")  # noqa: TRY003
        return replayed


def evaluate_proteotype_human_factors(
    request: object,
) -> ProteotypeHumanFactorsResult:
    """Public stateless M25-07 evaluation entry point."""

    return M2507HumanFactorsEngine().generate(request)


def preflight_m2507_authorization(candidate: object) -> None:
    """Reject denied controls before reading operational declarations."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, EvaluateProteotypeHumanFactorsRequest)
            else candidate.get("context")
            if isinstance(candidate, Mapping)
            else None
        )
        references = _member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": IdentityLineageState.RESOLVED.value,
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        authorized = all(
            _state_value(_member(references, role)) == state for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - fail closed at hostile mapping boundary.
        raise M2507AuthorizationError from None
    if not authorized:
        raise M2507AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _findings(
    request: EvaluateProteotypeHumanFactorsRequest,
) -> tuple[OperationalFinding, ...]:
    evidence = _evidence(request)
    findings: list[OperationalFinding] = []
    code_by_dimension = {
        "reviewer_comprehension": OperationalFindingCode.COMPREHENSION_FAILURE,
        "automation_bias": OperationalFindingCode.AUTOMATION_BIAS_RISK,
        "throughput": OperationalFindingCode.THROUGHPUT_FAILURE,
        "latency": OperationalFindingCode.LATENCY_FAILURE,
        "downtime": OperationalFindingCode.DOWNTIME_FAILURE,
        "recovery": OperationalFindingCode.RECOVERY_FAILURE,
        "fallback": OperationalFindingCode.FALLBACK_UNAVAILABLE,
    }
    findings.extend(
        OperationalFinding(
            finding_id=f"finding.metric.{metric.metric_id}",
            code=code_by_dimension[metric.dimension.value],
            message=f"Operational metric {metric.metric_id} is not passing.",
            evidence=evidence,
        )
        for metric in request.metrics
        if metric.status is not OperationalStatus.PASS
    )
    findings.extend(
        OperationalFinding(
            finding_id=f"finding.fallback.{scenario.scenario_id}",
            code=OperationalFindingCode.FALLBACK_UNAVAILABLE,
            message=f"Fallback scenario {scenario.scenario_id} is not passing.",
            evidence=evidence,
        )
        for scenario in request.fallbacks
        if scenario.status is not OperationalStatus.PASS
    )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _report(request: EvaluateProteotypeHumanFactorsRequest) -> HumanFactorsOperationalReport:
    digest = canonical_request_digest(request)
    return HumanFactorsOperationalReport(
        report_id="m2507.report." + digest.removeprefix("sha256:"),
        version=request.configuration.version,
        metrics=request.metrics,
        fallbacks=request.fallbacks,
        configuration=request.configuration,
        evidence=_evidence(request),
    )


def _support(*, completed: bool) -> SupportDecision:
    if completed:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="operational_evaluation_completed",
            rationale=(
                "Caller-declared operational metrics and fallback controls satisfy the "
                "provisional M25-07 boundary."
            ),
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="operational_evaluation_abstained",
        rationale=(
            "A human-factors or fallback declaration is not passing and is withheld for review."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M25-07 does not estimate {dimension} uncertainty from metadata-only inputs."
            ),
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Operational measurements and fallback labels are caller-declared; they do not "
            "establish deployment or clinical uncertainty.",
        ),
    )


def _evidence(
    request: EvaluateProteotypeHumanFactorsRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M25-07 operational artifact; issuer authority is not "
                "authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: EvaluateProteotypeHumanFactorsRequest,
    request_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=str(decision.state.value),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id="m2507.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2507_MODULE_ID,
        module_version=M2507_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            *tuple(artifact.digest for artifact in request.source_artifacts),
            request.upstream_result.digest,
            sha256_digest(request.configuration),
        ),
        configuration_digest=sha256_digest(
            {
                "configuration": request.configuration,
                "metrics": request.metrics,
                "fallbacks": request.fallbacks,
            }
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2507AuthorizationError",
    "M2507HumanFactorsEngine",
    "M2507ReplayError",
    "evaluate_proteotype_human_factors",
    "preflight_m2507_authorization",
]
