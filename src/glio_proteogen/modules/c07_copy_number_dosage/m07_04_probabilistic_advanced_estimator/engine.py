"""Deterministic, replay-verifiable M07-04 estimator boundary.

The dossier describes an advanced probabilistic estimator but does not freeze
the model registry, weights, feature catalogue, posterior semantics, or
endpoint ABI.  This implementation therefore executes a deliberately small
declaration-only proxy: a locked mechanism-guided configuration may project
finite caller-declared scalar/interval observations into typed estimates.
Every other family, optimizer, categorical observation, or malformed transport
is rejected or safely abstained.  No artifact is opened and no calibrated
probability is emitted.
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

from glio_proteogen.contracts.m07_04 import (
    M0704_CONTRACT_VERSION,
    M0704_EVIDENCE_CLAIM,
    M0704_MAX_CANONICAL_REQUEST_BYTES,
    M0704_MODULE_ID,
    EstimateCopyNumberDosageProbabilisticRequest,
    EstimateCopyNumberDosageProbabilisticResult,
    EstimatorObservation,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticEstimatorFamily,
    ProbabilisticResultStatus,
    canonical_request_digest,
    expected_uncertainty,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

M0704_PROXY_OPTIMIZER: Final = "locked_declaration_proxy_v1"
_REQUEST_ADAPTER: Final = TypeAdapter(EstimateCopyNumberDosageProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateCopyNumberDosageProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_EXPECTED_CONTROL_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}


class ProbabilisticEstimatorAuthorizationError(PermissionError):
    """Raised before unauthorized requests traverse representation metadata."""

    def __init__(self) -> None:
        super().__init__(
            "M07-04 requires accepted controls, resolved identity, and granted consent"
        )


class ProbabilisticEstimatorInputError(ValueError):
    """Raised for malformed or over-limit request transport."""

    def __init__(self, detail: str = "M07-04 request is invalid") -> None:
        super().__init__(detail)


class ProbabilisticEstimatorReplayError(ValueError):
    """Raised when a result cannot be reproduced from its exact request."""

    def __init__(self, detail: str = "verification failed") -> None:
        super().__init__(f"M07-04 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state_text(value: object) -> object:
    return getattr(value, "value", value)


def _plain_value(value: object) -> object:
    """Convert only strict JSON-like values for canonical transport."""

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
    """Reject denied controls before schema, observations, or artifacts are traversed."""

    if type(request) is not EstimateCopyNumberDosageProbabilisticRequest and not isinstance(
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
    except Exception:  # noqa: BLE001 - hostile values fail closed.
        raise ProbabilisticEstimatorAuthorizationError from None
    if states != _EXPECTED_CONTROL_STATES:
        raise ProbabilisticEstimatorAuthorizationError


def _validate_json_request(
    candidate: object,
    serialized: bytes | str,
) -> EstimateCopyNumberDosageProbabilisticRequest:
    if not isinstance(candidate, Mapping):
        raise ProbabilisticEstimatorInputError
    preflight_probabilistic_estimator_authorization(candidate)
    try:
        canonical = canonical_json_bytes(_plain_value(candidate))
        if len(canonical) > M0704_MAX_CANONICAL_REQUEST_BYTES:
            raise ProbabilisticEstimatorInputError
        strict_json_loads(serialized, max_bytes=M0704_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(serialized, strict=True)
    except ProbabilisticEstimatorAuthorizationError:
        raise
    except ProbabilisticEstimatorInputError:
        raise
    except Exception as error:
        raise ProbabilisticEstimatorInputError from error


def _prepare_request(candidate: object) -> EstimateCopyNumberDosageProbabilisticRequest:
    if type(candidate) is EstimateCopyNumberDosageProbabilisticRequest:
        preflight_probabilistic_estimator_authorization(candidate)
        raw = canonical_json_bytes(candidate.model_dump(mode="json"))
        if len(raw) > M0704_MAX_CANONICAL_REQUEST_BYTES:
            raise ProbabilisticEstimatorInputError
        try:
            return _REQUEST_ADAPTER.validate_json(raw, strict=True)
        except ValidationError as error:
            raise ProbabilisticEstimatorInputError from error
    if isinstance(candidate, bytes | bytearray | str):
        try:
            decoded: object = strict_json_loads(
                candidate,
                max_bytes=M0704_MAX_CANONICAL_REQUEST_BYTES,
            )
            if not isinstance(decoded, Mapping):
                raise ProbabilisticEstimatorInputError
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
    request: EstimateCopyNumberDosageProbabilisticRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        *tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=reference.decision_id,
                state=reference.state.value,
                policy_version=reference.policy_version,
                evidence_digest=reference.evidence.digest,
            )
            for role, reference in (
                (ControlRole.PROVENANCE, refs.provenance),
                (ControlRole.CONSENT, refs.consent),
                (ControlRole.QUALITY, refs.quality),
                (ControlRole.SUPPORT, refs.support),
                (ControlRole.INTENDED_USE, refs.intended_use),
            )
        ),
    )


def _provenance(
    request: EstimateCopyNumberDosageProbabilisticRequest,
    request_hash: str,
) -> ProvenanceRecord:
    input_digests = tuple(
        artifact.digest
        for artifact in (request.representation_result, *request.source_artifacts)
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0704.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0704_MODULE_ID,
        module_version=M0704_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.configuration.model_dump(mode="json")),
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(
    request: EstimateCopyNumberDosageProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=M0704_EVIDENCE_CLAIM,
        )
        for artifact in (request.representation_result, *request.source_artifacts)
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_proxy_not_calibrated",
            statement=(
                "The declaration-only projection is not a calibrated posterior or biological "
                "probability and must not be used as a treatment recommendation."
            ),
        ),
        Limitation(
            code="external_model_not_executed",
            statement=(
                "Caller artifacts are never opened; learned, graph, and mechanistic models "
                "are not executed at this provisional boundary."
            ),
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Source artifacts, observations, configuration, and controls are caller "
                "declared; issuer authority is not authenticated."
            ),
        ),
    )


def _posterior(observation: EstimatorObservation) -> PosteriorEstimate | None:
    if observation.scalar_value is not None:
        if not isfinite(observation.scalar_value):
            return None
        return PosteriorEstimate(
            feature_id=observation.feature_id,
            kind=PosteriorEstimateKind.SCALAR,
            unit=observation.unit,
            estimate_value=observation.scalar_value,
        )
    if observation.interval_lower is not None and observation.interval_upper is not None:
        center = (observation.interval_lower + observation.interval_upper) / 2.0
        if not all(
            isfinite(item)
            for item in (observation.interval_lower, observation.interval_upper, center)
        ):
            return None
        return PosteriorEstimate(
            feature_id=observation.feature_id,
            kind=PosteriorEstimateKind.INTERVAL,
            unit=observation.unit,
            estimate_value=center,
            lower_bound=observation.interval_lower,
            upper_bound=observation.interval_upper,
        )
    # Categorical observations cannot be converted to dosage without an
    # owner-approved calibration and therefore abstain rather than coerce.
    return None


def _posteriors(
    request: EstimateCopyNumberDosageProbabilisticRequest,
) -> tuple[PosteriorEstimate, ...] | None:
    estimates = tuple(_posterior(item) for item in request.observations)
    if any(item is None for item in estimates):
        return None
    return cast("tuple[PosteriorEstimate, ...]", estimates)


def _support(status: ProbabilisticResultStatus, reason: str) -> SupportDecision:
    if status is ProbabilisticResultStatus.ESTIMATED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="provisional_proxy_estimate",
            rationale=(
                "Accepted controls and finite numeric observations passed the locked "
                "declaration-only proxy; no model probability is claimed."
            ),
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="probabilistic_estimator_abstained",
        rationale=reason,
    )


def _diagnostic(
    request: EstimateCopyNumberDosageProbabilisticRequest,
    status: ProbabilisticResultStatus,
    reason: str,
) -> OptimizationDiagnostic:
    if status is ProbabilisticResultStatus.ESTIMATED:
        return OptimizationDiagnostic(
            diagnostic_id="diagnostic.m0704.proxy",
            status=OptimizationDiagnosticStatus.CONVERGED,
            objective=request.configuration.objective,
            iteration_count=0,
            objective_value=0.0,
            convergence_gap=0.0,
            message=(
                "Declaration-only deterministic projection completed; no trained model or "
                "calibrated probability was executed."
            ),
        )
    return OptimizationDiagnostic(
        diagnostic_id="diagnostic.m0704.abstain",
        status=OptimizationDiagnosticStatus.NOT_EVALUABLE,
        objective=request.configuration.objective,
        iteration_count=0,
        message=reason,
    )


def _build_result(
    request: EstimateCopyNumberDosageProbabilisticRequest,
) -> EstimateCopyNumberDosageProbabilisticResult:
    request_hash = canonical_request_digest(request)
    reason = (
        "The selected estimator family or optimizer is not authorized by the provisional "
        "M07-04 execution boundary."
    )
    estimates: tuple[PosteriorEstimate, ...] | None = None
    if (
        request.configuration.estimator_family is ProbabilisticEstimatorFamily.MECHANISM_GUIDED
        and request.configuration.optimizer == M0704_PROXY_OPTIMIZER
    ):
        estimates = _posteriors(request)
        if estimates is None:
            reason = (
                "At least one observation is categorical or non-finite for the numeric "
                "declaration-only dosage proxy; no negative finding is emitted."
            )
        elif not estimates:
            reason = "The request contains no estimable observations."
    status = (
        ProbabilisticResultStatus.ESTIMATED if estimates else ProbabilisticResultStatus.ABSTAINED
    )
    candidate = EstimateCopyNumberDosageProbabilisticResult.model_construct(
        result_id=f"result.{request_hash.removeprefix('sha256:')}",
        result_version=M0704_CONTRACT_VERSION,
        request_digest=request_hash,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        estimates=estimates or (),
        diagnostics=(_diagnostic(request, status, reason),),
        abstention_reason=None if status is ProbabilisticResultStatus.ESTIMATED else reason,
        parent_target="proteotype",
        emits_parent=False,
        support_decision=_support(status, reason),
        uncertainty=expected_uncertainty(),
        provenance=_provenance(request, request_hash),
        evidence=_evidence(request),
        limitations=_limitations(),
        human_review_required=status is not ProbabilisticResultStatus.ESTIMATED,
    )
    payload = candidate.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(candidate)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0704ProbabilisticEstimatorEngine:
    """Execute the provisional proxy or return a typed safe abstention."""

    __slots__ = ()

    @staticmethod
    def validate_request(request: object) -> EstimateCopyNumberDosageProbabilisticRequest:
        return _prepare_request(request)

    def estimate(self, request: object) -> EstimateCopyNumberDosageProbabilisticResult:
        return _build_result(_prepare_request(request))

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> EstimateCopyNumberDosageProbabilisticResult:
        """Verify the self-digest and optionally replay the exact request."""

        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except ValidationError as error:
            raise ProbabilisticEstimatorReplayError from error
        if not verify_result_digest(typed):
            raise ProbabilisticEstimatorReplayError
        if replay:
            replayed = self.estimate(typed.request)
            if replayed != typed:
                raise ProbabilisticEstimatorReplayError
        return typed


def estimate_copy_number_dosage_probabilistic(
    request: object,
) -> EstimateCopyNumberDosageProbabilisticResult:
    """Estimate one strict request, abstaining when the proxy cannot run."""

    return M0704ProbabilisticEstimatorEngine().estimate(request)


__all__ = [
    "M0704_PROXY_OPTIMIZER",
    "M0704ProbabilisticEstimatorEngine",
    "ProbabilisticEstimatorAuthorizationError",
    "ProbabilisticEstimatorInputError",
    "ProbabilisticEstimatorReplayError",
    "estimate_copy_number_dosage_probabilistic",
    "preflight_probabilistic_estimator_authorization",
]
