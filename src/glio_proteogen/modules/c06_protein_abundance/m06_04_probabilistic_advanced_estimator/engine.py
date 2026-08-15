"""Strict, deterministic M06-04 estimator boundary.

The dossier names a probabilistic/advanced estimator, but does not authorize a
model registry, weights, calibration set, or posterior semantics. This
boundary implements a declaration-only proxy for one locked mechanism-guided
configuration and abstains for every other family or unsupported representation.
It never opens caller artifacts or treats a caller-declared probability as
calibrated evidence.
"""

# The transport preparation path intentionally enumerates hostile input shapes.
# ruff: noqa: C901, PLR0911, TRY301

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from math import isfinite
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from glio_proteogen.contracts.m06_01.v1 import FormalStateMissingness
from glio_proteogen.contracts.m06_04 import (
    M0604_CONTRACT_VERSION,
    M0604_EVIDENCE_CLAIM,
    M0604_MAX_CANONICAL_REQUEST_BYTES,
    M0604_MODULE_ID,
    EstimateProteinAbundanceProbabilisticRequest,
    EstimateProteinAbundanceProbabilisticResult,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticEstimatorFamily,
    ProbabilisticResultStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinAbundanceProbabilisticRequest)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0604_PROXY_OPTIMIZER: Final = "deterministic_proxy_v1"
_AUTHORIZATION_MESSAGE: Final = "M06-04 probabilistic request is not authorized"
_INPUT_MESSAGE: Final = "M06-04 request failed strict validation"
_EXPECTED_CONTROL_STATES: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class ProbabilisticEstimatorAuthorizationError(PermissionError):
    """Raised before an unauthorized posterior request traverses inputs."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class ProbabilisticEstimatorInputError(ValueError):
    """Raised for malformed input without reflecting caller payloads."""

    def __init__(self) -> None:
        super().__init__(_INPUT_MESSAGE)


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    if isinstance(candidate, BaseModel):
        return getattr(candidate, field, None)
    return None


def _state_text(value: object) -> str | None:
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else None


def _plain_value(value: object) -> object:
    """Convert only finite JSON-like values accepted at the transport edge."""

    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Enum):
        return _plain_value(value.value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if value is None or type(value) in {str, int, float, bool}:
        return value
    if type(value) is list:
        return [_plain_value(item) for item in cast("list[object]", value)]
    if type(value) is tuple:
        return tuple(_plain_value(item) for item in cast("tuple[object, ...]", value))
    if type(value) is dict:
        result: dict[str, object] = {}
        for key, item in cast("dict[object, object]", value).items():
            if type(key) is not str:
                raise ProbabilisticEstimatorInputError
            result[key] = _plain_value(item)
        return result
    raise ProbabilisticEstimatorInputError


def preflight_probabilistic_estimator_authorization(request: object) -> None:
    """Reject denied controls before schema, values, or artifacts are traversed."""

    if type(request) is not EstimateProteinAbundanceProbabilisticRequest and not isinstance(
        request, Mapping
    ):
        raise ProbabilisticEstimatorAuthorizationError
    try:
        context = _member(request, "context")
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROL_STATES
        }
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise ProbabilisticEstimatorAuthorizationError from None
    if states != _EXPECTED_CONTROL_STATES:
        raise ProbabilisticEstimatorAuthorizationError


def _validate_json_request(
    candidate: object,
    serialized: bytes | str,
) -> EstimateProteinAbundanceProbabilisticRequest:
    if not isinstance(candidate, Mapping):
        raise ProbabilisticEstimatorInputError
    preflight_probabilistic_estimator_authorization(candidate)
    try:
        canonical = canonical_json_bytes(_plain_value(candidate))
        if len(canonical) > M0604_MAX_CANONICAL_REQUEST_BYTES:
            raise ProbabilisticEstimatorInputError
        strict_json_loads(serialized, max_bytes=M0604_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(serialized, strict=True)
    except ProbabilisticEstimatorAuthorizationError:
        raise
    except ProbabilisticEstimatorInputError:
        raise
    except Exception as error:
        raise ProbabilisticEstimatorInputError from error


def _prepare_request(candidate: object) -> EstimateProteinAbundanceProbabilisticRequest:
    if type(candidate) is EstimateProteinAbundanceProbabilisticRequest:
        preflight_probabilistic_estimator_authorization(candidate)
        raw = canonical_json_bytes(candidate.model_dump(mode="json"))
        if len(raw) > M0604_MAX_CANONICAL_REQUEST_BYTES:
            raise ProbabilisticEstimatorInputError
        try:
            return _REQUEST_ADAPTER.validate_json(raw, strict=True)
        except ValidationError as error:
            raise ProbabilisticEstimatorInputError from error
    if isinstance(candidate, bytes | bytearray | str):
        try:
            decoded: object = strict_json_loads(
                candidate,
                max_bytes=M0604_MAX_CANONICAL_REQUEST_BYTES,
            )
            if not isinstance(decoded, Mapping):
                raise ProbabilisticEstimatorInputError
            preflight_probabilistic_estimator_authorization(decoded)
            serialized = candidate if isinstance(candidate, str) else bytes(candidate)
            return _validate_json_request(decoded, serialized)
        except ProbabilisticEstimatorAuthorizationError:
            raise
        except ProbabilisticEstimatorInputError:
            raise
        except (ValidationError, TypeError, ValueError) as error:
            raise ProbabilisticEstimatorInputError from error
    if isinstance(candidate, Mapping):
        preflight_probabilistic_estimator_authorization(candidate)
        try:
            raw = canonical_json_bytes(_plain_value(candidate))
        except ProbabilisticEstimatorInputError:
            raise
        except (TypeError, ValueError) as error:
            raise ProbabilisticEstimatorInputError from error
        return _validate_json_request(candidate, raw)
    raise ProbabilisticEstimatorInputError


def _control_decisions(
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        *tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=role_reference.decision_id,
                state=role_reference.state.value,
                policy_version=role_reference.policy_version,
                evidence_digest=role_reference.evidence.digest,
            )
            for role, role_reference in (
                (ControlRole.PROVENANCE, references.provenance),
                (ControlRole.CONSENT, references.consent),
                (ControlRole.QUALITY, references.quality),
                (ControlRole.SUPPORT, references.support),
                (ControlRole.INTENDED_USE, references.intended_use),
            )
        ),
    )


def _provenance(
    request: EstimateProteinAbundanceProbabilisticRequest,
    request_hash: str,
) -> ProvenanceRecord:
    configuration_digest = sha256_digest(request.configuration.model_dump(mode="json"))
    input_digests = tuple(
        artifact.digest for artifact in (*request.source_artifacts, request.representation_artifact)
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0604.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0604_MODULE_ID,
        module_version=M0604_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=configuration_digest,
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=M0604_EVIDENCE_CLAIM,
        )
        for artifact in request.source_artifacts
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M06-04 calibration and uncertainty decomposition are not frozen; "
            "no probability is emitted by this provisional boundary."
        ),
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
            "Deterministic proxy intervals are not calibrated posterior intervals.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_proxy_not_calibrated",
            statement=(
                "Any estimate is a deterministic declaration-only proxy, not a calibrated "
                "posterior or biological probability."
            ),
        ),
        Limitation(
            code="external_model_not_executed",
            statement=(
                "Caller artifacts are never opened; learned, proteoform, and external "
                "mechanistic models are not executed at this boundary."
            ),
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Source artifacts, configuration, and controls are caller-declared; issuer "
                "authority is not authenticated."
            ),
        ),
    )


def _numeric_value(value: object) -> tuple[float, PosteriorEstimateKind] | None:
    state = getattr(value, "state", None)
    if state is not FormalStateMissingness.OBSERVED:
        return None
    scalar = getattr(value, "scalar_value", None)
    if scalar is not None:
        return (scalar, PosteriorEstimateKind.SCALAR) if isfinite(scalar) else None
    lower = getattr(value, "interval_lower", None)
    upper = getattr(value, "interval_upper", None)
    if lower is None or upper is None or not all(isfinite(item) for item in (lower, upper)):
        return None
    return ((lower + upper) / 2.0, PosteriorEstimateKind.INTERVAL)


def _estimates(
    request: EstimateProteinAbundanceProbabilisticRequest,
) -> tuple[PosteriorEstimate, ...] | None:
    definitions = {item.feature_id: item for item in request.state_schema.features}
    estimates: list[PosteriorEstimate] = []
    for value in request.feature_values:
        numeric = _numeric_value(value)
        if numeric is None:
            return None
        center, kind = numeric
        if kind is PosteriorEstimateKind.SCALAR:
            estimates.append(
                PosteriorEstimate(
                    feature_id=value.feature_id,
                    kind=kind,
                    unit=definitions[value.feature_id].unit,
                    estimate_value=center,
                )
            )
            continue
        lower = value.interval_lower
        upper = value.interval_upper
        if lower is None or upper is None:
            return None
        estimates.append(
            PosteriorEstimate(
                feature_id=value.feature_id,
                kind=kind,
                unit=definitions[value.feature_id].unit,
                estimate_value=center,
                lower_bound=lower,
                upper_bound=upper,
            )
        )
    return tuple(estimates)


def _support(status: ProbabilisticResultStatus, reason: str) -> SupportDecision:
    if status is ProbabilisticResultStatus.ESTIMATED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="provisional_proxy_estimate",
            rationale=(
                "All declared controls passed and the locked deterministic proxy accepted "
                "the observed numeric representation."
            ),
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="probabilistic_estimator_abstained",
        rationale=reason,
    )


def _diagnostic(
    request: EstimateProteinAbundanceProbabilisticRequest,
    status: ProbabilisticResultStatus,
    reason: str,
) -> OptimizationDiagnostic:
    if status is ProbabilisticResultStatus.ESTIMATED:
        return OptimizationDiagnostic(
            diagnostic_id="diagnostic.m0604.proxy",
            status=OptimizationDiagnosticStatus.CONVERGED,
            objective=request.configuration.objective,
            iteration_count=0,
            objective_value=0.0,
            convergence_gap=0.0,
            message=(
                "Declaration-only deterministic proxy completed; no trained model or "
                "calibrated probability was executed."
            ),
        )
    return OptimizationDiagnostic(
        diagnostic_id="diagnostic.m0604.abstain",
        status=OptimizationDiagnosticStatus.NOT_EVALUABLE,
        objective=request.configuration.objective,
        iteration_count=0,
        message=reason,
    )


class M0604ProbabilisticEstimatorEngine:
    """Execute the provisional proxy or return a typed safe abstention."""

    __slots__ = ()

    @staticmethod
    def validate_request(request: object) -> EstimateProteinAbundanceProbabilisticRequest:
        return _prepare_request(request)

    def estimate(self, request: object) -> EstimateProteinAbundanceProbabilisticResult:
        canonical = _prepare_request(request)
        request_hash = canonical_request_digest(canonical)
        reason = (
            "The selected estimator family or optimizer is not authorized by the provisional "
            "M06-04 execution boundary."
        )
        estimates: tuple[PosteriorEstimate, ...] | None = None
        if (
            canonical.configuration.estimator_family
            is ProbabilisticEstimatorFamily.MECHANISM_GUIDED
            and canonical.configuration.optimizer == M0604_PROXY_OPTIMIZER
        ):
            estimates = _estimates(canonical)
            if estimates is not None:
                reason = "Observed values are outside the numeric declaration-only proxy domain."
        status = (
            ProbabilisticResultStatus.ESTIMATED
            if estimates
            else ProbabilisticResultStatus.ABSTAINED
        )
        diagnostic = _diagnostic(canonical, status, reason)
        candidate = EstimateProteinAbundanceProbabilisticResult.model_construct(
            result_id=f"result.m0604.{request_hash.removeprefix('sha256:')}",
            result_version=M0604_CONTRACT_VERSION,
            request_digest=request_hash,
            result_digest=_ZERO_DIGEST,
            request=canonical,
            status=status,
            estimates=estimates or (),
            diagnostics=(diagnostic,),
            abstention_reason=None if status is ProbabilisticResultStatus.ESTIMATED else reason,
            parent_target="biomarker_panel",
            emits_parent=False,
            support_decision=_support(status, reason),
            uncertainty=_uncertainty(),
            provenance=_provenance(canonical, request_hash),
            evidence=_evidence(canonical),
            limitations=_limitations(),
        )
        payload = candidate.model_dump(mode="python")
        payload["result_digest"] = result_payload_digest(candidate)
        return EstimateProteinAbundanceProbabilisticResult.model_validate(payload, strict=True)


def estimate_protein_abundance_probabilistic(
    request: object,
) -> EstimateProteinAbundanceProbabilisticResult:
    """Estimate from one strict request, abstaining when the proxy cannot run."""

    return M0604ProbabilisticEstimatorEngine().estimate(request)


__all__ = [
    "M0604_PROXY_OPTIMIZER",
    "M0604ProbabilisticEstimatorEngine",
    "ProbabilisticEstimatorAuthorizationError",
    "ProbabilisticEstimatorInputError",
    "estimate_protein_abundance_probabilistic",
    "preflight_probabilistic_estimator_authorization",
]
