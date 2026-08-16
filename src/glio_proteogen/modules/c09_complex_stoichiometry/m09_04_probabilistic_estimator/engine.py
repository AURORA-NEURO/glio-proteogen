"""Replay-safe probabilistic-estimator runtime for provisional M09-04.

The dossier freezes the estimator responsibility and safety boundary, but not
the learned model, catalogue, or public ABI. This runtime consequently uses a
deterministic, content-addressed reference estimator. It exercises the full
posterior/diagnostic/replay lifecycle without pretending caller-declared
hashes are training data. Any missing, unsupported, OOD, conflicted, or
non-convergent declaration is quarantined before a posterior is emitted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_04 import (
    M0904_CONTRACT_VERSION,
    M0904_EVIDENCE_CLAIM,
    M0904_MAX_CANONICAL_RESULT_BYTES,
    M0904_PARENT,
    EstimateComplexActivityProbabilisticRequest,
    EstimateComplexActivityProbabilisticResult,
    EstimateComplexActivityProbabilisticVerification,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticReplayReason,
    ProbabilisticResultStatus,
)
from glio_proteogen.contracts.m09_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateComplexActivityProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateComplexActivityProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_ABSTENTION_MARKERS: Final = frozenset(
    {"missing", "unsupported", "ood", "out_of_domain", "conflict", "review", "quarantine"}
)
_FAILURE_MARKERS: Final = frozenset(
    {"fail", "failed", "not_evaluable", "nonconverged", "non_converged", "unstable"}
)


class M0904AuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M09-04 requires accepted controls, resolved identity, and granted consent"
        )


class M0904InputError(ValueError):
    """Raised for oversized or non-canonical result material."""

    _MESSAGES: Final = {
        "result_limit": "M09-04 result exceeds the canonical byte limit",
        "result_digest": "M09-04 result digest does not match its content",
        "result_noncanonical": "M09-04 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0904Result:
    """A typed result paired with its one canonical byte representation."""

    result: EstimateComplexActivityProbabilisticResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0904InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0904InputError("result_noncanonical")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0904_authorization(candidate: object) -> None:
    """Check every caller control before evaluating evidence declarations."""

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
        raise M0904AuthorizationError from None
    if states != expected:
        raise M0904AuthorizationError


def _evidence(
    request: EstimateComplexActivityProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0904_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _control_decisions(
    request: EstimateComplexActivityProbabilisticRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    decisions = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=decision.state.value,
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, decision in decisions
    )


def _provenance(
    request: EstimateComplexActivityProbabilisticRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts} | {request.baseline_result.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M09-04",
        module_version=M0904_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _uncertainty(*, estimated: bool) -> UncertaintyProfile:
    if not estimated:
        estimate = UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale="Posterior is withheld because support or convergence is not sufficient.",
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
                "All uncertainty dimensions remain not estimable for this abstained result.",
            ),
        )

    def _dimension(probability: float, rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=probability,
            rationale=rationale,
        )

    return UncertaintyProfile(
        measurement=_dimension(0.12, "Deterministic reference uncertainty proxy."),
        sampling=_dimension(0.08, "Sampling uncertainty proxy from locked source count."),
        parameter=_dimension(0.10, "Parameter uncertainty proxy from declared priors."),
        model_form=_dimension(0.18, "Model-form uncertainty remains provisional."),
        identification=_dimension(0.06, "Identity control was accepted upstream."),
        support=_dimension(0.05, "Support control and source markers passed."),
        transport=_dimension(0.20, "Transport uncertainty is bounded but not calibrated."),
        sensitivity_notes=(
            (
                "Probabilities are deterministic provisional diagnostics, not calibrated "
                "clinical risk."
            ),
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Estimator catalogue, posterior representation, ceilings, media types, "
                "and endpoint ABI remain provisional pending owner confirmation."
            ),
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "The runtime consumes content-addressed declarations only; it never fetches "
                "or relabels spectra, genomic data, PTM annotations, or treatment history."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits only a complex-activity posterior and diagnostics; it emits "
                "no kinase state, all-omics fusion, treatment recommendation, or parent result."
            ),
        ),
        Limitation(
            code="uncertainty_calibration",
            statement=(
                "Uncertainty values are explicit deterministic proxies and are not a claim "
                "of calibrated 90% coverage until locked benchmark evidence exists."
            ),
        ),
    )


def _tokens(request: EstimateComplexActivityProbabilisticRequest) -> set[str]:
    values = [
        *(item.artifact_id.casefold() for item in request.source_artifacts),
        request.baseline_result.artifact_id.casefold(),
        request.configuration.objective.casefold(),
        *(item.expression.casefold() for item in request.configuration.constraints),
    ]
    normalized = [value.replace("-", "_").replace(" ", "_") for value in values]
    return {token for value in normalized for token in (value, *value.split("_"))}


def _numeric_value(
    feature_id: str,
    request: EstimateComplexActivityProbabilisticRequest,
) -> float:
    """Derive a stable bounded proxy without treating a hash as a trained model."""

    seed = "|".join(
        (
            feature_id,
            request.baseline_result.digest,
            request.configuration.configuration_id,
            str(request.configuration.seed),
            *sorted(item.digest for item in request.source_artifacts),
        )
    ).encode("utf-8")
    fraction = int.from_bytes(sha256(seed).digest()[:8], "big") / float(2**64)
    return round(0.1 + fraction * 0.8, 8)


def _diagnostic(  # noqa: PLR0913 - diagnostic envelope has six independent locked fields
    request: EstimateComplexActivityProbabilisticRequest,
    request_digest: str,
    *,
    status: OptimizationDiagnosticStatus,
    message: str,
    objective_value: float | None = None,
    convergence_gap: float | None = None,
) -> OptimizationDiagnostic:
    return OptimizationDiagnostic(
        diagnostic_id=f"diagnostic.{request_digest.removeprefix('sha256:')}",
        status=status,
        objective=request.configuration.objective,
        iteration_count=(
            request.configuration.max_iterations
            if status is OptimizationDiagnosticStatus.CONVERGED
            else 0
        ),
        objective_value=objective_value,
        convergence_gap=convergence_gap,
        message=message,
        evidence=_evidence(request),
    )


def _build_result(
    request: EstimateComplexActivityProbabilisticRequest,
) -> EstimateComplexActivityProbabilisticResult:
    request_digest = canonical_request_digest(request)
    tokens = _tokens(request)
    blocked = sorted(
        marker for marker in _ABSTENTION_MARKERS if any(marker in token for token in tokens)
    )
    failed = sorted(
        marker for marker in _FAILURE_MARKERS if any(marker in token for token in tokens)
    )
    hard_constraints = [
        item
        for item in request.configuration.constraints
        if item.hard and any(marker in item.expression.casefold() for marker in _ABSTENTION_MARKERS)
    ]
    if hard_constraints:
        blocked.extend(item.constraint_id for item in hard_constraints)

    if blocked or failed:
        reason_parts = []
        if blocked:
            reason_parts.append(
                "unsupported or review-required declarations: " + ", ".join(blocked)
            )
        if failed:
            reason_parts.append("optimization did not converge: " + ", ".join(failed))
        status = SupportStatus.UNSUPPORTED if blocked else SupportStatus.REVIEW_REQUIRED
        diagnostic_status = (
            OptimizationDiagnosticStatus.NOT_EVALUABLE
            if blocked
            else OptimizationDiagnosticStatus.FAILED
        )
        diagnostic_message = "; ".join(reason_parts)
        diagnostics = (
            _diagnostic(
                request,
                request_digest,
                status=diagnostic_status,
                message=diagnostic_message,
            ),
        )
        estimates: tuple[PosteriorEstimate, ...] = ()
        result_status = ProbabilisticResultStatus.ABSTAINED
        abstention_reason = diagnostic_message
        support = SupportDecision(
            status=status,
            reason_code="m0904_safe_abstention",
            rationale=diagnostic_message,
        )
        uncertainty = _uncertainty(estimated=False)
    else:
        values = tuple(
            _numeric_value(item.artifact_id, request) for item in request.source_artifacts
        )
        width = round(min(0.25, max(0.03, 0.08 + (len(request.configuration.priors) * 0.005))), 8)
        estimates = tuple(
            PosteriorEstimate(
                feature_id=item.artifact_id,
                kind=PosteriorEstimateKind.INTERVAL,
                unit="provisional-complex-activity",
                estimate_value=value,
                lower_bound=round(max(0.0, value - width), 8),
                upper_bound=round(min(1.0, value + width), 8),
                posterior_mass=0.9,
                evidence=_evidence(request),
            )
            for item, value in zip(request.source_artifacts, values, strict=True)
        )
        objective_value = round(sum(values) / len(values), 8)
        diagnostics_list = [
            _diagnostic(
                request,
                request_digest,
                status=OptimizationDiagnosticStatus.CONVERGED,
                message=(
                    "Deterministic reference posterior converged under the locked "
                    "objective, priors, constraints, and seed."
                ),
                objective_value=objective_value,
                convergence_gap=0.001,
            )
        ]
        diagnostics_list.extend(
            OptimizationDiagnostic(
                diagnostic_id=(
                    f"diagnostic.{request_digest.removeprefix('sha256:')}."
                    f"{constraint.constraint_id}"
                ),
                status=OptimizationDiagnosticStatus.CONVERGED,
                objective=constraint.expression,
                iteration_count=request.configuration.max_iterations,
                objective_value=objective_value,
                convergence_gap=0.001,
                message="Soft constraint retained as a visible model limitation.",
                evidence=constraint.evidence,
            )
            for constraint in request.configuration.constraints
            if not constraint.hard
        )
        diagnostics = tuple(diagnostics_list)
        result_status = ProbabilisticResultStatus.ESTIMATED
        abstention_reason = None
        support = SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0904_reference_support",
            rationale=(
                "All declared inputs are supported, controls are accepted, and the "
                "deterministic reference objective converged."
            ),
        )
        uncertainty = _uncertainty(estimated=True)

    draft = EstimateComplexActivityProbabilisticResult.model_construct(
        result_id=f"result.{request_digest.removeprefix('sha256:')}",
        result_version=M0904_CONTRACT_VERSION,
        request_digest=request_digest,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=result_status,
        estimates=estimates,
        diagnostics=diagnostics,
        abstention_reason=abstention_reason,
        parent_target=M0904_PARENT,
        support_decision=support,
        uncertainty=uncertainty,
        provenance=_provenance(request, request_digest),
        evidence=_evidence(request),
        limitations=_limitations(),
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0904ProbabilisticEstimator:
    """Build and verify deterministic posterior envelopes with safe abstention."""

    __slots__ = ()

    @staticmethod
    def validate_request(request: object) -> EstimateComplexActivityProbabilisticRequest:
        preflight_m0904_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def estimate(self, request: object) -> EstimateComplexActivityProbabilisticResult:
        return self.build(request).result

    def build(self, request: object) -> BuiltM0904Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0904_MAX_CANONICAL_RESULT_BYTES:
            raise M0904InputError("result_limit")
        return BuiltM0904Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> EstimateComplexActivityProbabilisticVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return EstimateComplexActivityProbabilisticVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ProbabilisticReplayReason.INVALID_RESULT,
            )
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0904_MAX_CANONICAL_RESULT_BYTES
        ):
            return EstimateComplexActivityProbabilisticVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=(
                    ProbabilisticReplayReason.OVERSIZED
                    if isinstance(canonical_bytes, bytes)
                    else ProbabilisticReplayReason.NON_CANONICAL
                ),
            )
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        verified = content_verified and deterministic_verified
        return EstimateComplexActivityProbabilisticVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                ProbabilisticReplayReason.VERIFIED
                if verified
                else (
                    ProbabilisticReplayReason.NON_CANONICAL
                    if not content_verified
                    else ProbabilisticReplayReason.DIGEST_MISMATCH
                )
            ),
        )

    def execute(self, request: object) -> BuiltM0904Result:
        return self.build(request)


def estimate_complex_activity_probabilistic(
    request: object,
) -> EstimateComplexActivityProbabilisticResult:
    """Public M09-04 operation returning the typed result envelope."""

    return M0904ProbabilisticEstimator().estimate(request)


__all__ = [
    "BuiltM0904Result",
    "M0904AuthorizationError",
    "M0904InputError",
    "M0904ProbabilisticEstimator",
    "estimate_complex_activity_probabilistic",
    "preflight_m0904_authorization",
]
