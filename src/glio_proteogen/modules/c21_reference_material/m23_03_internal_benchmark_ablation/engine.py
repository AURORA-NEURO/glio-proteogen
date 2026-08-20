"""Deterministic, caller-declared M23-03 benchmark and ablation runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_03 import (
    M2303_CONTRACT_VERSION,
    M2303_EVIDENCE_CLAIM,
    M2303_MODULE_ID,
    BaselineKind,
    BenchmarkDossier,
    BenchmarkFinding,
    BenchmarkFindingCode,
    BenchmarkMetric,
    BenchmarkStatus,
    RunVariantPeptideInternalBenchmarkRequest,
    ValidationStatus,
    VariantPeptideInternalBenchmarkResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(RunVariantPeptideInternalBenchmarkRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M23-03 benchmarking requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M23-02 synthetic-truth result is caller-declared; issuer authority and source "
            "content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="metadata_only_benchmark",
        statement=(
            "The benchmark compares caller-declared scores, metrics, and compute units; it does "
            "not run a biological model or emit a variant-peptide estimate."
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


class M2303AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize benchmarking."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2303ReplayError(ValueError):
    """Raised when a benchmark result fails canonical replay verification."""

    def __init__(self, message: str = "M23-03 canonical replay verification failed") -> None:
        super().__init__(message)


class M2303BenchmarkEngine:
    """Build and replay one deterministic metadata-only benchmark dossier."""

    __slots__ = ()

    def generate(self, request: object) -> VariantPeptideInternalBenchmarkResult:
        preflight_m2303_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        if _contains_not_evaluable(canonical):
            return _result(
                canonical,
                request_digest,
                status=BenchmarkStatus.ABSTAINED,
                dossier=None,
                findings=(),
                abstention_reason=(
                    "At least one benchmark metric, ablation, or comparison is not evaluable; "
                    "M23-03 abstains without converting missing evidence to a negative finding."
                ),
                support_status=SupportStatus.REVIEW_REQUIRED,
            )
        dossier = _dossier(canonical)
        return _result(
            canonical,
            request_digest,
            status=BenchmarkStatus.COMPLETED,
            dossier=dossier,
            findings=_findings(canonical),
            abstention_reason=None,
            support_status=SupportStatus.SUPPORTED,
        )

    def replay(
        self,
        result: VariantPeptideInternalBenchmarkResult,
    ) -> VariantPeptideInternalBenchmarkResult:
        """Regenerate the benchmark result and compare its full canonical payload.

        The digest checks below reject malformed identity fields with stable errors for
        callers.  They are not sufficient on their own: a caller could mutate a dossier
        or evidence record and then recompute ``result_digest``.  Revalidating the
        submitted result and regenerating it from the request closes that semantic
        self-rehash gap while preserving the provisional metadata-only ABI.
        """
        if result.request_digest != canonical_request_digest(result.request):
            raise M2303ReplayError("M23-03 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2303ReplayError("M23-03 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2303ReplayError("M23-03 result payload digest mismatch")  # noqa: TRY003
        try:
            canonical_result = VariantPeptideInternalBenchmarkResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            regenerated = self.generate(canonical_result.request)
        except Exception as error:
            raise M2303ReplayError from error
        if canonical_json_bytes(canonical_result) != canonical_json_bytes(regenerated):
            raise M2303ReplayError
        return canonical_result


def run_variant_peptide_internal_benchmark(
    request: object,
) -> VariantPeptideInternalBenchmarkResult:
    """Public stateless M23-03 benchmark entry point."""

    return M2303BenchmarkEngine().generate(request)


def preflight_m2303_authorization(candidate: object) -> None:
    """Reject denied controls before reading benchmark material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, RunVariantPeptideInternalBenchmarkRequest)
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
        raise M2303AuthorizationError from None
    if not authorized:
        raise M2303AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _contains_not_evaluable(request: RunVariantPeptideInternalBenchmarkRequest) -> bool:
    return (
        any(
            item.status is ValidationStatus.NOT_EVALUABLE
            for baseline in request.baseline_runs
            for item in baseline.metrics
        )
        or any(item.status is ValidationStatus.NOT_EVALUABLE for item in request.ablations)
        or any(item.status is ValidationStatus.NOT_EVALUABLE for item in request.comparisons)
    )


def _dossier(request: RunVariantPeptideInternalBenchmarkRequest) -> BenchmarkDossier:
    simple = next(item for item in request.baseline_runs if item.kind is BaselineKind.SIMPLE)
    mature = next(item for item in request.baseline_runs if item.kind is BaselineKind.MATURE)
    simple_metric = simple.metrics[0]
    mature_metric = mature.metrics[0]
    lower_is_better = simple_metric.lower_is_better and mature_metric.lower_is_better
    tolerance = max(simple_metric.tolerance, mature_metric.tolerance)
    difference = mature_metric.candidate_value - simple_metric.baseline_value
    within_tolerance = difference >= -tolerance if lower_is_better else difference <= tolerance
    summary = BenchmarkMetric(
        metric_id="m2303.summary.metric",
        metric_name="simple_to_mature_baseline_comparison",
        baseline_value=simple_metric.baseline_value,
        candidate_value=mature_metric.candidate_value,
        tolerance=tolerance,
        lower_is_better=lower_is_better,
        status=ValidationStatus.PASS if within_tolerance else ValidationStatus.FAIL,
        evidence=_evidence(request),
    )
    request_digest = canonical_request_digest(request)
    return BenchmarkDossier(
        dossier_id="m2303.dossier." + request_digest.removeprefix("sha256:"),
        version=request.split.version,
        split=request.split,
        baselines=request.baseline_runs,
        ablations=request.ablations,
        comparisons=request.comparisons,
        metrics=(summary,),
        evidence=_evidence(request),
    )


def _findings(request: RunVariantPeptideInternalBenchmarkRequest) -> tuple[BenchmarkFinding, ...]:
    findings: list[BenchmarkFinding] = []
    findings.extend(
        BenchmarkFinding(
            finding_id=f"{baseline.run_id}.{metric.metric_id}.failure",
            code=BenchmarkFindingCode.BASELINE_FAILURE,
            message=(f"Baseline metric {metric.metric_id} failed its declared criterion."),
            evidence=_evidence(request),
        )
        for baseline in request.baseline_runs
        for metric in baseline.metrics
        if metric.status is ValidationStatus.FAIL
    )
    findings.extend(
        BenchmarkFinding(
            finding_id=f"{ablation.ablation_id}.failure",
            code=BenchmarkFindingCode.ABLATION_FAILURE,
            message=f"Ablation {ablation.ablation_id} failed its declared criterion.",
            evidence=_evidence(request),
        )
        for ablation in request.ablations
        if ablation.status is ValidationStatus.FAIL
    )
    findings.extend(
        BenchmarkFinding(
            finding_id=f"{comparison.comparison_id}.failure",
            code=BenchmarkFindingCode.COMPUTE_MISMATCH,
            message=(
                f"Compute-matched comparison {comparison.comparison_id} failed its "
                "declared criterion."
            ),
            evidence=_evidence(request),
        )
        for comparison in request.comparisons
        if comparison.status is ValidationStatus.FAIL
    )
    return tuple(findings)


def _result(  # noqa: PLR0913
    request: RunVariantPeptideInternalBenchmarkRequest,
    request_digest: str,
    *,
    status: BenchmarkStatus,
    dossier: BenchmarkDossier | None,
    findings: tuple[BenchmarkFinding, ...],
    abstention_reason: str | None,
    support_status: SupportStatus,
) -> VariantPeptideInternalBenchmarkResult:
    payload: dict[str, Any] = {
        "output_type": "variant_peptide_internal_benchmark",
        "result_id": result_identifier(request),
        "result_version": M2303_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": "sha256:" + ("0" * 64),
        "request": request,
        "status": status,
        "dossier": dossier,
        "findings": findings,
        "abstention_reason": abstention_reason,
        "parent_target": "variant peptide",
        "emits_parent": False,
        "support_decision": _support(support_status),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request, request_digest),
        "evidence": _evidence(request),
        "limitations": _LIMITATIONS,
        "human_review_required": status is BenchmarkStatus.ABSTAINED,
    }
    provisional = VariantPeptideInternalBenchmarkResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(provisional)
    return VariantPeptideInternalBenchmarkResult.model_validate_json(
        canonical_json_bytes(payload), strict=True
    )


def _support(status: SupportStatus) -> SupportDecision:
    return SupportDecision(
        status=status,
        reason_code=(
            "deterministic_benchmark_completed"
            if status is SupportStatus.SUPPORTED
            else "benchmark_not_evaluable"
        ),
        rationale=(
            "Caller-declared locked split, simple and mature baselines, ablations, and "
            "compute-matched comparisons satisfy the provisional M23-03 boundary."
            if status is SupportStatus.SUPPORTED
            else "At least one caller-declared benchmark component requires review before use."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M23-03 does not estimate {dimension} uncertainty from metadata-only inputs."
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
    request: RunVariantPeptideInternalBenchmarkRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M2303_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(
    request: RunVariantPeptideInternalBenchmarkRequest,
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
        activity_id="m2303.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2303_MODULE_ID,
        module_version=M2303_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
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
    "M2303AuthorizationError",
    "M2303BenchmarkEngine",
    "M2303ReplayError",
    "preflight_m2303_authorization",
    "run_variant_peptide_internal_benchmark",
]
