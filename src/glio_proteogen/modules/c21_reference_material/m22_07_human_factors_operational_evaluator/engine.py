"""Deterministic, caller-declared M22-07 operational evaluation runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_07 import (
    M2207_CONTRACT_VERSION,
    M2207_MODULE_ID,
    EvaluateProteinRnaDiscordanceHumanFactorsRequest,
    EvaluationStatus,
    HumanFactorsOperationalReport,
    OperationalDimension,
    OperationalFinding,
    OperationalFindingCode,
    OperationalStatus,
    ProteinRnaDiscordanceHumanFactorsResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinRnaDiscordanceHumanFactorsRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M22-07 operational evaluation requires accepted configuration, resolved identity, granted "
    "consent, accepted provenance/quality/support/intended-use controls"
)
_SEMANTIC_REPLAY_MESSAGE: Final = "M22-07 replay output differs from deterministic regeneration"
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "M22-06 is accepted only as a caller-declared media boundary; issuer authority and "
            "source content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="metadata_only_operational",
        statement=(
            "The evaluator reports caller-declared reviewer comprehension, automation bias, "
            "throughput, latency, downtime, recovery, and fallback material."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "Kinase activity, generic all-omics fusion, treatment recommendation, identity or "
            "consent inference, and unsupported-to-negative conversion are outside this module."
        ),
    ),
)


class M2207AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize evaluation."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2207ReplayError(ValueError):
    """Raised when an evaluation result fails canonical replay verification."""


class M2207OperationalEngine:
    """Build and replay one deterministic metadata-only operational evaluation."""

    __slots__ = ()

    def generate(self, request: object) -> ProteinRnaDiscordanceHumanFactorsResult:
        preflight_m2207_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        report = HumanFactorsOperationalReport(
            report_id="m2207.report." + request_digest.removeprefix("sha256:"),
            version=canonical.configuration.version,
            metrics=canonical.metrics,
            fallbacks=canonical.fallbacks,
            configuration=canonical.configuration,
            evidence=_evidence(canonical),
        )
        unsupported = _unsupported_reason(canonical)
        if unsupported is None:
            status = EvaluationStatus.EVALUATED
            output_report: HumanFactorsOperationalReport | None = report
            findings = _findings(canonical)
            abstention_reason: str | None = None
            support = _support()
        else:
            status = EvaluationStatus.ABSTAINED
            output_report = None
            findings = (
                OperationalFinding(
                    finding_id="m2207.finding.not-evaluable",
                    code=OperationalFindingCode.UPSTREAM_UNSUPPORTED,
                    message=unsupported,
                    evidence=_evidence(canonical),
                ),
            )
            abstention_reason = unsupported
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="operational_material_not_evaluable",
                rationale=unsupported,
            )
        payload: dict[str, Any] = {
            "output_type": "protein_rna_discordance_human_factors_operational",
            "result_id": result_identifier(canonical),
            "result_version": M2207_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "report": output_report,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "protein-RNA discordance",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        provisional = ProteinRnaDiscordanceHumanFactorsResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteinRnaDiscordanceHumanFactorsResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self,
        result: ProteinRnaDiscordanceHumanFactorsResult,
    ) -> ProteinRnaDiscordanceHumanFactorsResult:
        # Preserve the existing direct digest failures before parsing the full
        # envelope, so callers receive precise closure errors for forged IDs or
        # digests rather than a generic validation failure.
        if result.request_digest != canonical_request_digest(result.request):
            raise M2207ReplayError("M22-07 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2207ReplayError("M22-07 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2207ReplayError("M22-07 result payload digest mismatch")  # noqa: TRY003
        try:
            replayed = ProteinRnaDiscordanceHumanFactorsResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
        except Exception as error:
            raise M2207ReplayError from error
        try:
            expected = self.generate(replayed.request)
        except Exception as error:
            raise M2207ReplayError from error
        if expected.model_dump(mode="json") != replayed.model_dump(mode="json"):
            raise M2207ReplayError(_SEMANTIC_REPLAY_MESSAGE)
        return replayed


def evaluate_protein_rna_discordance_human_factors_operational(
    request: object,
) -> ProteinRnaDiscordanceHumanFactorsResult:
    """Public stateless M22-07 evaluation entry point."""

    return M2207OperationalEngine().generate(request)


def preflight_m2207_authorization(candidate: object) -> None:
    """Reject denied controls before reading caller-declared operational material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, EvaluateProteinRnaDiscordanceHumanFactorsRequest)
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
        raise M2207AuthorizationError from None
    if not authorized:
        raise M2207AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _unsupported_reason(
    request: EvaluateProteinRnaDiscordanceHumanFactorsRequest,
) -> str | None:
    if any(item.status is OperationalStatus.NOT_EVALUABLE for item in request.metrics):
        return "one or more operational metrics are not evaluable"
    if any(item.status is OperationalStatus.NOT_EVALUABLE for item in request.fallbacks):
        return "one or more fallback scenarios are not evaluable"
    return None


def _findings(
    request: EvaluateProteinRnaDiscordanceHumanFactorsRequest,
) -> tuple[OperationalFinding, ...]:
    metric_codes = {
        OperationalDimension.REVIEWER_COMPREHENSION: OperationalFindingCode.COMPREHENSION_FAILURE,
        OperationalDimension.AUTOMATION_BIAS: OperationalFindingCode.AUTOMATION_BIAS_RISK,
        OperationalDimension.THROUGHPUT: OperationalFindingCode.THROUGHPUT_FAILURE,
        OperationalDimension.LATENCY: OperationalFindingCode.LATENCY_FAILURE,
        OperationalDimension.DOWNTIME: OperationalFindingCode.DOWNTIME_FAILURE,
        OperationalDimension.RECOVERY: OperationalFindingCode.RECOVERY_FAILURE,
        OperationalDimension.FALLBACK: OperationalFindingCode.FALLBACK_UNAVAILABLE,
    }
    metric_findings = [
        OperationalFinding(
            finding_id="m2207.finding." + metric.metric_id,
            code=metric_codes[metric.dimension],
            message=f"operational metric {metric.metric_id} failed its declared target",
            evidence=metric.evidence,
        )
        for metric in request.metrics
        if metric.status is OperationalStatus.FAIL
    ]
    fallback_findings = [
        OperationalFinding(
            finding_id="m2207.finding." + fallback.scenario_id,
            code=OperationalFindingCode.FALLBACK_UNAVAILABLE,
            message=f"fallback scenario {fallback.scenario_id} requires review",
            evidence=fallback.evidence,
        )
        for fallback in request.fallbacks
        if fallback.status is OperationalStatus.FAIL or not fallback.fallback_available
    ]
    return (*metric_findings, *fallback_findings)


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="operational_evaluation_completed",
        rationale=(
            "Caller-declared M22-07 operational material satisfied the provisional evaluation "
            "boundary without unsupported-to-negative conversion."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M22-07 does not estimate {dimension} uncertainty from caller-declared inputs."
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
            "Operational evidence is caller-declared and does not establish biological or "
            "clinical uncertainty.",
        ),
    )


def _evidence(
    request: EvaluateProteinRnaDiscordanceHumanFactorsRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M22-07 operational evidence; issuer authority is not "
                "authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: EvaluateProteinRnaDiscordanceHumanFactorsRequest,
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
        activity_id="m2207.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2207_MODULE_ID,
        module_version=M2207_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
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
    "M2207AuthorizationError",
    "M2207OperationalEngine",
    "M2207ReplayError",
    "evaluate_protein_rna_discordance_human_factors_operational",
    "preflight_m2207_authorization",
]
