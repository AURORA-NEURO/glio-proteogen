"""Deterministic, caller-declared M21-03 benchmark and ablation runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_03 import (
    M2103_CONTRACT_VERSION,
    M2103_MODULE_ID,
    BenchmarkDossier,
    BenchmarkStatus,
    ComplexActivityInternalBenchmarkResult,
    RunComplexActivityInternalBenchmarkRequest,
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

_REQUEST_ADAPTER: Final = TypeAdapter(RunComplexActivityInternalBenchmarkRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M21-03 benchmarking requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_upstream",
        statement=(
            "The M21-02 synthetic-truth result is caller-declared; issuer authority and source "
            "content are not authenticated or traversed."
        ),
    ),
    Limitation(
        code="metadata_only_benchmark",
        statement=(
            "The benchmark compares caller-declared scores and compute units; it does not run "
            "a biological model or emit a complex-activity estimate."
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


class M2103AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize benchmarking."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2103ReplayError(ValueError):
    """Raised when a benchmark result fails canonical replay verification."""


class M2103Engine:
    """Build and replay one deterministic metadata-only benchmark dossier."""

    __slots__ = ()

    def generate(self, request: object) -> ComplexActivityInternalBenchmarkResult:
        preflight_m2103_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        dossier = BenchmarkDossier(
            dossier_id="m2103.dossier." + request_digest.removeprefix("sha256:"),
            version=canonical.split.version,
            split=canonical.split,
            baselines=canonical.baseline_runs,
            ablations=canonical.ablations,
            comparisons=canonical.comparisons,
            metrics=tuple(
                metric for baseline in canonical.baseline_runs for metric in baseline.metrics
            ),
            evidence=_evidence(canonical),
        )
        payload: dict[str, Any] = {
            "output_type": "complex_activity_internal_benchmark",
            "result_id": result_identifier(canonical),
            "result_version": M2103_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": BenchmarkStatus.COMPLETED,
            "dossier": dossier,
            "findings": (),
            "abstention_reason": None,
            "parent_target": "complex activity",
            "emits_parent": False,
            "support_decision": _support(),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": False,
        }
        provisional = ComplexActivityInternalBenchmarkResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ComplexActivityInternalBenchmarkResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def replay(
        self,
        result: ComplexActivityInternalBenchmarkResult,
    ) -> ComplexActivityInternalBenchmarkResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2103ReplayError("M21-03 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2103ReplayError("M21-03 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2103ReplayError("M21-03 result payload digest mismatch")  # noqa: TRY003
        return ComplexActivityInternalBenchmarkResult.model_validate_json(
            canonical_json_bytes(result), strict=True
        )


def run_complex_activity_internal_benchmark(
    request: object,
) -> ComplexActivityInternalBenchmarkResult:
    """Public stateless M21-03 benchmark entry point."""

    return M2103Engine().generate(request)


def preflight_m2103_authorization(candidate: object) -> None:
    """Reject denied controls before reading benchmark material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, RunComplexActivityInternalBenchmarkRequest)
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
        raise M2103AuthorizationError from None
    if not authorized:
        raise M2103AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    actual = _member(candidate, "state")
    return getattr(actual, "value", actual)


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="deterministic_benchmark_completed",
        rationale=(
            "Caller-declared locked split, baselines, ablations, and compute-matched comparisons "
            "satisfy the provisional M21-03 boundary."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=(
                f"M21-03 does not estimate {dimension} uncertainty from metadata-only inputs."
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
    request: RunComplexActivityInternalBenchmarkRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M21-03 benchmark artifact; issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: RunComplexActivityInternalBenchmarkRequest,
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
        activity_id="m2103.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2103_MODULE_ID,
        module_version=M2103_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            *tuple(artifact.digest for artifact in request.source_artifacts),
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
    "M2103AuthorizationError",
    "M2103Engine",
    "M2103ReplayError",
    "preflight_m2103_authorization",
    "run_complex_activity_internal_benchmark",
]
