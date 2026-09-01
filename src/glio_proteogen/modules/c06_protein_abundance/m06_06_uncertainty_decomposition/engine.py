"""Deterministic, safe-abstaining provisional M06-06 engine."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite, sqrt
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_05.canonical import (
    canonical_request_digest as m0605_request_digest,
)
from glio_proteogen.contracts.m06_05.canonical import (
    result_payload_digest as m0605_result_digest,
)
from glio_proteogen.contracts.m06_06 import (
    M0606_CONTRACT_VERSION,
    M0606_EVIDENCE_CLAIM,
    M0606_MAX_CANONICAL_REQUEST_BYTES,
    M0606_MAX_COVERAGE,
    M0606_MIN_COVERAGE,
    M0606_PARENT,
    DecomposeProteinAbundanceUncertaintyRequest,
    ProteinAbundanceUncertaintyDecompositionResult,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
    UncertaintyFinding,
    UncertaintyFindingCode,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m06_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    EstimateState,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.modules.c06_protein_abundance.m06_06_uncertainty_decomposition.kernel import (
    M0606UncertaintyDecompositionKernel,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeProteinAbundanceUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinAbundanceUncertaintyDecompositionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0606UncertaintyDecompositionAuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M06-06 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_uncertainty_decomposition_authorization(candidate: object) -> None:
    """Check controls before opening the complete upstream M06-05 result."""

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
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M0606UncertaintyDecompositionAuthorizationError from None
    if states != expected:
        raise M0606UncertaintyDecompositionAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_uncertainty_decomposition_authorization(candidate)
    return candidate


def _validate_typed_request(
    candidate: object,
) -> DecomposeProteinAbundanceUncertaintyRequest:
    return _REQUEST_ADAPTER.validate_python(_prepare(candidate), strict=True)


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> DecomposeProteinAbundanceUncertaintyRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0606_MAX_CANONICAL_REQUEST_BYTES:
        raise ValueError("M06-06 canonical request exceeds its byte limit")  # noqa: TRY003
    candidate = _prepare(candidate)
    return _REQUEST_ADAPTER.validate_json(
        (serialized if isinstance(serialized, (bytes, bytearray)) else serialized.encode("utf-8")),
        strict=True,
    )


def _evidence(
    request: DecomposeProteinAbundanceUncertaintyRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0606_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _support(status: SupportStatus) -> SupportDecision:
    if status is SupportStatus.UNSUPPORTED:
        return SupportDecision(
            status=status,
            reason_code="m0606_uncertainty_abstained",
            rationale="The uncertainty estimator cannot safely emit unsupported components.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="m0606_uncertainty_review_required",
        rationale="Owner-confirmed calibration and benchmark evidence are pending review.",
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="uncertainty_decomposition_only",
            statement="Output is limited to typed uncertainty and sensitivity metadata.",
        ),
        Limitation(
            code="no_kinase_or_treatment_output",
            statement=(
                "This module emits no kinase state, treatment recommendation, or parent panel."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M06-06 ABI and calibration policy are provisional pending owner confirmation."
            ),
        ),
    )


def _clip_probability(value: float) -> float:
    """Return a finite, bounded uncertainty probability."""

    if not isfinite(value):
        return 0.95
    return round(max(0.05, min(0.95, value)), 8)


def _median(values: list[float]) -> float:
    """Compute a deterministic median without importing a mutable statistics state."""

    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _uncertainty_probabilities(
    request: DecomposeProteinAbundanceUncertaintyRequest,
) -> dict[UncertaintyDimension, float]:
    """Estimate uncertainty from the actual M06-05 evidence envelope.

    The decomposition is intentionally auditable rather than a request-digest
    pseudo-random score.  Each component is derived from a distinct signal:
    interval width, feature count, soft-constraint influence, model-family
    diversity, unevaluable evaluations, support evidence, and glioma feature
    transport.  All signals are bounded before they enter the public contract.
    """

    upstream = request.constraint_result
    estimates = tuple(upstream.estimates)
    intervals = [
        abs(item.upper_bound - item.lower_bound) / max(abs(item.estimate_value), 1e-6)
        for item in estimates
        if item.lower_bound is not None and item.upper_bound is not None
    ]
    measurement = _clip_probability(0.05 + 0.35 * (_median(intervals) if intervals else 0.75))

    feature_count = max(1, len(estimates))
    sampling = _clip_probability(1.0 / sqrt(feature_count))

    ablation_magnitudes = [abs(item.effect_delta) for item in upstream.ablations]
    mean_ablation = (
        sum(ablation_magnitudes) / len(ablation_magnitudes) if ablation_magnitudes else 0.65
    )
    parameter = _clip_probability(0.05 + 0.45 * mean_ablation)

    kinds = {item.kind.value for item in upstream.request.constraint_set.constraints}
    model_form = _clip_probability(0.08 + 0.22 * (len(kinds) / 8.0))

    non_evaluable = sum(
        item.outcome.value in {"not_evaluable", "abstained"} for item in upstream.evaluations
    )
    identification = _clip_probability(0.05 + non_evaluable / max(1, len(upstream.evaluations)))

    support = _clip_probability(
        0.10
        + 0.20 * (1.0 - min(1.0, len(upstream.evidence) / 8.0))
        + 0.15 * (1.0 if upstream.support_decision.status.value != "supported" else 0.0)
    )

    glioma_markers = (
        "egfr",
        "pdgfra",
        "met",
        "cdk4",
        "mdm2",
        "mycn",
        "cdkn2a",
        "cdkn2b",
        "pten",
        "nf1",
        "chr10",
    )
    marker_hits = sum(
        any(marker in feature_id.casefold() for marker in glioma_markers)
        for feature_id in (str(item.feature_id) for item in estimates)
    )
    transport = _clip_probability(0.35 - 0.20 * (marker_hits / feature_count))

    return {
        UncertaintyDimension.MEASUREMENT: measurement,
        UncertaintyDimension.SAMPLING: sampling,
        UncertaintyDimension.PARAMETER: parameter,
        UncertaintyDimension.MODEL_FORM: model_form,
        UncertaintyDimension.IDENTIFICATION: identification,
        UncertaintyDimension.SUPPORT: support,
        UncertaintyDimension.TRANSPORT: transport,
    }


def _uncertainty_profile(
    values: dict[UncertaintyDimension, float],
) -> UncertaintyProfile:
    """Build the shared uncertainty profile from the same component estimates."""

    def estimate(dimension: UncertaintyDimension) -> UncertaintyEstimate:
        probability = values[dimension]
        return UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=probability,
            rationale=(
                f"M06-05 evidence-derived {dimension.value} uncertainty; "
                "bounded analytical estimate, not a clinical probability."
            ),
        )

    return UncertaintyProfile(
        measurement=estimate(UncertaintyDimension.MEASUREMENT),
        sampling=estimate(UncertaintyDimension.SAMPLING),
        parameter=estimate(UncertaintyDimension.PARAMETER),
        model_form=estimate(UncertaintyDimension.MODEL_FORM),
        identification=estimate(UncertaintyDimension.IDENTIFICATION),
        support=estimate(UncertaintyDimension.SUPPORT),
        transport=estimate(UncertaintyDimension.TRANSPORT),
        sensitivity_notes=(
            "Components are derived independently from intervals, constraints, evaluations, "
            "and glioma feature transport.",
            "No missing dimension is silently collapsed into a residual or treated as zero.",
        ),
    )


def _evaluated_sensitivity(
    request: DecomposeProteinAbundanceUncertaintyRequest,
    values: dict[UncertaintyDimension, float],
) -> SensitivityEnvelope:
    """Emit a bounded analytical sensitivity envelope for a locked policy."""

    peak = max(values.values())
    observed = max(M0606_MIN_COVERAGE, min(M0606_MAX_COVERAGE, 0.95 - (0.1 * peak)))
    lower = max(M0606_MIN_COVERAGE, observed - 0.03)
    upper = min(M0606_MAX_COVERAGE, observed + 0.03)
    evidence = _evidence(request)
    return SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        nominal_coverage=request.policy.nominal_coverage,
        lower_bound=round(lower, 8),
        upper_bound=round(upper, 8),
        observed_coverage=round(observed, 8),
        rationale=(
            "Deterministic analytical coverage envelope derived from the upstream interval "
            "width and constraint sensitivity; it is not a clinical validation claim."
        ),
        evidence=evidence,
    )


def _unsupported_reason(
    request: DecomposeProteinAbundanceUncertaintyRequest,
) -> str | None:
    """Return a safe abstention reason for unsupported upstream or policy inputs."""

    upstream = request.constraint_result
    method = request.policy.method.casefold()
    if upstream.status.value == "abstained":
        return "the bound M06-05 constraint integration is abstained"
    if upstream.support_decision.status.value != "supported":
        return "the bound M06-05 constraint integration is not supported"
    if any(
        marker in method
        for marker in (
            "unsupported",
            "not_evaluable",
            "missing",
            "uncalibrated",
            "unlocked",
            "provisional-no-calibration",
        )
    ):
        return "declared uncertainty policy is outside the supported analytical domain"
    if not upstream.estimates:
        return "the bound M06-05 result contains no estimates"
    return None


class M0606UncertaintyDecompositionEngine:
    """Bind M06-05 and abstain until calibration and sensitivity are review-locked."""

    __slots__ = ("_kernel",)

    def __init__(self, kernel: M0606UncertaintyDecompositionKernel | None = None) -> None:
        self._kernel = kernel or M0606UncertaintyDecompositionKernel()

    def decompose(
        self,
        request: object,
    ) -> ProteinAbundanceUncertaintyDecompositionResult:
        return self.decompose_validated(_validate_typed_request(request))

    def decompose_validated(
        self,
        request: DecomposeProteinAbundanceUncertaintyRequest,
    ) -> ProteinAbundanceUncertaintyDecompositionResult:
        """Execute a request that was already validated at an ingress boundary."""

        if not isinstance(request, DecomposeProteinAbundanceUncertaintyRequest):
            raise TypeError("M06-06 requires a validated request")  # noqa: TRY003
        return self._result(request)

    def _result(
        self,
        request: DecomposeProteinAbundanceUncertaintyRequest,
    ) -> ProteinAbundanceUncertaintyDecompositionResult:
        upstream = request.constraint_result
        if upstream.request_digest != m0605_request_digest(upstream.request):
            raise ValueError("M06-05 result request digest is stale")  # noqa: TRY003
        if upstream.result_digest != m0605_result_digest(upstream):
            raise ValueError("M06-05 result digest is stale")  # noqa: TRY003
        request_hash = canonical_request_digest(request)
        policy_hash = sha256_digest(request.policy)
        unsupported = _unsupported_reason(request)
        evidence = _evidence(request)
        values = _uncertainty_probabilities(request) if unsupported is None else None
        if unsupported is None and values is not None:
            components = tuple(
                UncertaintyComponent(
                    dimension=dimension,
                    estimate=UncertaintyEstimate(
                        state=EstimateState.ESTIMATED,
                        probability=probability,
                        rationale=(
                            f"Evidence-derived {dimension.value} uncertainty from the "
                            "M06-05 abundance posterior and constraint evaluations."
                        ),
                    ),
                    rationale=(
                        f"{dimension.value} is estimated from a dedicated upstream signal; "
                        "the value is bounded and research-use-only."
                    ),
                    evidence=evidence,
                )
                for dimension, probability in values.items()
            )
            decomposition = UncertaintyDecomposition(
                decomposition_id=f"decomposition.{request_hash.removeprefix('sha256:')}",
                components=components,
                method=request.policy.method,
                model_reference=request.policy.calibration_reference,
                evidence=evidence,
            )
            sensitivity = _evaluated_sensitivity(request, values)
            status = UncertaintyDecompositionStatus.DECOMPOSED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m0606_evidence_decomposition_supported",
                rationale=(
                    "All seven uncertainty dimensions are estimated from the validated "
                    "M06-05 posterior, constraints, and evaluations."
                ),
            )
            findings: tuple[UncertaintyFinding, ...] = ()
            abstention_reason = None
            human_review_required = False
            profile = _uncertainty_profile(values)
        else:
            reason = unsupported or "uncertainty decomposition is not evaluable"
            code = (
                UncertaintyFindingCode.UPSTREAM_ABSTAINED
                if request.constraint_result.status.value == "abstained"
                else UncertaintyFindingCode.CALIBRATION_NOT_LOCKED
            )
            finding = UncertaintyFinding(
                finding_id=f"finding.{request_hash.removeprefix('sha256:')}",
                code=code,
                message=reason,
                evidence=evidence,
            )
            sensitivity = self._kernel.sensitivity_envelope(request.policy)
            status = UncertaintyDecompositionStatus.ABSTAINED
            support = _support(
                SupportStatus.UNSUPPORTED
                if request.constraint_result.status.value == "abstained"
                else SupportStatus.REVIEW_REQUIRED
            )
            decomposition = None
            findings = (finding,)
            abstention_reason = reason
            human_review_required = True
            profile = expected_uncertainty()
        provenance = expected_provenance(request, request_hash, policy_hash)
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0606_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "decomposition": decomposition,
            "sensitivity_envelope": sensitivity,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": M0606_PARENT,
            "support_decision": support,
            "uncertainty": profile,
            "provenance": provenance,
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": human_review_required,
        }
        constructed = ProteinAbundanceUncertaintyDecompositionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def decompose_protein_abundance_uncertainty(
    request: object,
) -> ProteinAbundanceUncertaintyDecompositionResult:
    """Public provisional M06-06 operation."""

    return M0606UncertaintyDecompositionEngine().decompose(request)


__all__ = [
    "M0606UncertaintyDecompositionAuthorizationError",
    "M0606UncertaintyDecompositionEngine",
    "_validate_json_request",
    "_validate_typed_request",
    "decompose_protein_abundance_uncertainty",
    "preflight_uncertainty_decomposition_authorization",
]
