"""Deterministic, caller-declared M25-03 benchmark and ablation runtime.

The engine compares only typed, caller-declared benchmark metadata. It never
traverses the M25-02 payload, runs a model, authenticates an issuer, or emits
proteotype or biological truth. Unsupported and non-passing benchmark states
remain explicit abstentions.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_03 import (
    M2503_CONTRACT_VERSION,
    M2503_MODULE_ID,
    BenchmarkDossier,
    BenchmarkFinding,
    BenchmarkFindingCode,
    BenchmarkStatus,
    ProteotypeInternalBenchmarkResult,
    RunProteotypeInternalBenchmarkRequest,
    ValidationStatus,
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

_REQUEST_ADAPTER: Final = TypeAdapter(RunProteotypeInternalBenchmarkRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M25-03 benchmarking requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_SEMANTIC_REPLAY_MESSAGE: Final = "M25-03 replay output differs from deterministic regeneration"
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M25-02 synthetic-truth result is caller-declared; issuer authority and source "
            "content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="metadata_only_benchmark",
        statement=(
            "The benchmark compares caller-declared scores and compute units; it does not run "
            "a protein-interaction model or emit a proteotype estimate."
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


class M2503AuthorizationError(ValueError):
    """Raised when caller-declared upstream controls do not authorize execution."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2503ReplayError(ValueError):
    """Raised when an immutable benchmark result fails canonical replay."""

    def __init__(self, message: str = "M25-03 replay verification failed") -> None:
        super().__init__(message)


class M2503BenchmarkEngine:
    """Build and replay one deterministic metadata-only benchmark dossier."""

    __slots__ = ()

    def generate(self, request: object) -> ProteotypeInternalBenchmarkResult:
        preflight_m2503_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        dossier = None if findings else _dossier(canonical, request_digest)
        status = BenchmarkStatus.COMPLETED if dossier is not None else BenchmarkStatus.ABSTAINED
        payload: dict[str, Any] = {
            "output_type": "proteotype_internal_benchmark",
            "result_id": result_identifier(canonical, status.value),
            "result_version": M2503_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "dossier": dossier,
            "findings": findings,
            "abstention_reason": None
            if dossier is not None
            else "Benchmark was not safely evaluable under the declared controls.",
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": _support(completed=dossier is not None),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": dossier is None,
        }
        provisional = ProteotypeInternalBenchmarkResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteotypeInternalBenchmarkResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self,
        result: ProteotypeInternalBenchmarkResult,
    ) -> ProteotypeInternalBenchmarkResult:
        """Validate and semantically regenerate one immutable result.

        The payload digest is an integrity check, not proof that the payload was
        produced by this engine: an attacker who can edit a nested dossier or
        provenance record can also recompute that digest.  Keep the cheap
        request/result closure checks first so malformed or directly forged
        digests retain their existing failure behavior, then regenerate from
        the bound request and compare the complete canonical result.
        """
        try:
            replayed = ProteotypeInternalBenchmarkResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
        except Exception as error:
            raise M2503ReplayError from error
        if replayed.request_digest != canonical_request_digest(replayed.request):
            raise M2503ReplayError
        if replayed.result_id != result_identifier(replayed.request, replayed.status.value):
            raise M2503ReplayError
        if replayed.result_digest != result_payload_digest(replayed):
            raise M2503ReplayError
        try:
            expected = self.generate(replayed.request)
        except Exception as error:
            raise M2503ReplayError from error
        if expected.model_dump(mode="json") != replayed.model_dump(mode="json"):
            raise M2503ReplayError(_SEMANTIC_REPLAY_MESSAGE)
        return replayed


def run_proteotype_internal_benchmark(
    request: object,
) -> ProteotypeInternalBenchmarkResult:
    """Public stateless M25-03 benchmark entry point."""

    return M2503BenchmarkEngine().generate(request)


def preflight_m2503_authorization(candidate: object) -> None:
    """Reject denied controls before reading benchmark declarations."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, RunProteotypeInternalBenchmarkRequest)
            else candidate.get("context")
            if type(candidate) is dict
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
        raise M2503AuthorizationError from None
    if not authorized:
        raise M2503AuthorizationError


def _member(candidate: object, field: str) -> object:
    if type(candidate) is dict:
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _findings(
    request: RunProteotypeInternalBenchmarkRequest,
) -> tuple[BenchmarkFinding, ...]:
    evidence = _evidence(request)
    findings: list[BenchmarkFinding] = []
    for baseline in request.baseline_runs:
        findings.extend(
            [
                BenchmarkFinding(
                    finding_id=f"finding.baseline.{metric.metric_id}",
                    code=BenchmarkFindingCode.BASELINE_FAILURE,
                    message=f"Baseline metric {metric.metric_id} is not passing.",
                    evidence=evidence,
                )
                for metric in baseline.metrics
                if metric.status is not ValidationStatus.PASS
            ]
        )
    findings.extend(
        [
            BenchmarkFinding(
                finding_id=f"finding.ablation.{ablation.ablation_id}",
                code=BenchmarkFindingCode.ABLATION_FAILURE,
                message=f"Ablation {ablation.ablation_id} is not passing.",
                evidence=evidence,
            )
            for ablation in request.ablations
            if ablation.status is not ValidationStatus.PASS
        ]
    )
    findings.extend(
        [
            BenchmarkFinding(
                finding_id=f"finding.comparison.{comparison.comparison_id}",
                code=BenchmarkFindingCode.COMPUTE_MISMATCH,
                message=(f"Compute-matched comparison {comparison.comparison_id} is not passing."),
                evidence=evidence,
            )
            for comparison in request.comparisons
            if comparison.status is not ValidationStatus.PASS
        ]
    )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _dossier(
    request: RunProteotypeInternalBenchmarkRequest,
    request_digest: str,
) -> BenchmarkDossier:
    return BenchmarkDossier(
        dossier_id="m2503.dossier." + request_digest.removeprefix("sha256:"),
        version=request.split.version,
        split=request.split,
        baselines=request.baseline_runs,
        ablations=request.ablations,
        comparisons=request.comparisons,
        metrics=tuple(metric for baseline in request.baseline_runs for metric in baseline.metrics),
        evidence=_evidence(request),
    )


def _support(*, completed: bool) -> SupportDecision:
    if completed:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="deterministic_benchmark_completed",
            rationale=(
                "Caller-declared locked split, baseline, ablation, and compute-matched "
                "comparison controls satisfy the provisional M25-03 boundary."
            ),
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="benchmark_abstained",
        rationale="A non-passing benchmark declaration remains withheld for review.",
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M25-03 does not estimate {dimension} uncertainty from metadata-only inputs."
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
            "Benchmark evidence is caller-declared and does not establish biological uncertainty.",
        ),
    )


def _evidence(
    request: RunProteotypeInternalBenchmarkRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M25-03 benchmark artifact; issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: RunProteotypeInternalBenchmarkRequest,
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
        activity_id="m2503.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2503_MODULE_ID,
        module_version=M2503_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            *tuple(artifact.digest for artifact in request.source_artifacts),
            request.upstream_result.digest,
            sha256_digest(request.split),
        ),
        configuration_digest=sha256_digest(
            {
                "split": request.split,
                "baselines": request.baseline_runs,
                "ablations": request.ablations,
                "comparisons": request.comparisons,
            }
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2503AuthorizationError",
    "M2503BenchmarkEngine",
    "M2503ReplayError",
    "preflight_m2503_authorization",
    "run_proteotype_internal_benchmark",
]
