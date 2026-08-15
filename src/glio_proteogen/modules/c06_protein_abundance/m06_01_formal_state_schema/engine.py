"""Deterministic M06-01 formal-state validation and invariant execution."""

# The public boundary intentionally catches hostile caller objects and converts them to
# non-reflecting typed errors. The expression evaluator is a closed comparison grammar.
# ruff: noqa: PLR0911, TRY301

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from glio_proteogen.contracts.m06_01 import (
    M0601_CONTRACT_VERSION,
    M0601_EVIDENCE_CLAIM,
    M0601_MAX_CANONICAL_REQUEST_BYTES,
    M0601_MODULE_ID,
    FormalStateFeatureValue,
    FormalStateInvariantResult,
    FormalStateInvariantStatus,
    FormalStateMissingness,
    FormalStateValidationStatus,
    ValidateFormalProteinStateRequest,
    ValidateFormalProteinStateResult,
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
from glio_proteogen.kernel.strict_json import strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateFormalProteinStateRequest)
_AUTHORIZATION_MESSAGE: Final = "M06-01 formal-state validation requires accepted upstream controls"
_INPUT_MESSAGE: Final = "M06-01 request failed strict validation"
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MIN_QUOTED_LITERAL_LENGTH: Final = 2
_EXPECTED_CONTROL_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_COMPARISON = re.compile(
    r"^(?P<feature>[A-Za-z0-9_.-]+)\s*(?P<operator>>=|<=|==|!=|>|<)\s*(?P<literal>.+)$"
)


class FormalStateAuthorizationError(PermissionError):
    """Authorization failed before schema, values, or artifacts were traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class FormalStateInputError(ValueError):
    """A candidate request failed strict validation without reflecting caller payloads."""

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
    if isinstance(value, BaseModel):
        return value
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
                raise FormalStateInputError
            result[key] = _plain_value(item)
        return result
    raise FormalStateInputError


def preflight_formal_state_authorization(candidate: object) -> None:
    """Reject denied controls before opening the schema, values, or source artifacts."""

    if type(candidate) is not ValidateFormalProteinStateRequest and not isinstance(
        candidate, Mapping
    ):
        raise FormalStateAuthorizationError
    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROL_STATES
        }
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise FormalStateAuthorizationError from None
    if states != _EXPECTED_CONTROL_STATES:
        raise FormalStateAuthorizationError


def _validate_json_request(
    candidate: object, serialized: bytes | str
) -> ValidateFormalProteinStateRequest:
    if not isinstance(candidate, Mapping):
        raise FormalStateInputError
    preflight_formal_state_authorization(candidate)
    try:
        canonical = canonical_json_bytes(_plain_value(candidate))
        if len(canonical) > M0601_MAX_CANONICAL_REQUEST_BYTES:
            raise FormalStateInputError
        strict_json_loads(serialized, max_bytes=M0601_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(serialized, strict=True)
    except FormalStateAuthorizationError:
        raise
    except FormalStateInputError:
        raise
    except Exception as error:
        raise FormalStateInputError from error


def _prepare_request(candidate: object) -> ValidateFormalProteinStateRequest:
    if type(candidate) is ValidateFormalProteinStateRequest:
        preflight_formal_state_authorization(candidate)
        raw = canonical_json_bytes(candidate.model_dump(mode="json"))
        if len(raw) > M0601_MAX_CANONICAL_REQUEST_BYTES:
            raise FormalStateInputError
        return _REQUEST_ADAPTER.validate_json(raw, strict=True)
    if isinstance(candidate, bytes | bytearray | str):
        try:
            decoded: object = strict_json_loads(
                candidate,
                max_bytes=M0601_MAX_CANONICAL_REQUEST_BYTES,
            )
            if not isinstance(decoded, Mapping):
                raise FormalStateInputError
            preflight_formal_state_authorization(decoded)
            serialized = candidate if isinstance(candidate, str) else bytes(candidate)
            return _validate_json_request(decoded, serialized)
        except FormalStateAuthorizationError:
            raise
        except FormalStateInputError:
            raise
        except (ValidationError, ValueError, TypeError) as error:
            raise FormalStateInputError from error
    if isinstance(candidate, Mapping):
        preflight_formal_state_authorization(candidate)
        raw = canonical_json_bytes(_plain_value(candidate))
        return _validate_json_request(candidate, raw)
    raise FormalStateInputError


def _value_lookup(request: ValidateFormalProteinStateRequest) -> dict[str, FormalStateFeatureValue]:
    return {item.feature_id: item for item in request.values}


def _literal(raw: str) -> float | str | None:
    stripped = raw.strip()
    if (
        len(stripped) >= _MIN_QUOTED_LITERAL_LENGTH
        and stripped[0] == stripped[-1]
        and stripped[0] in {"'", '"'}
    ):
        return stripped[1:-1]
    try:
        return float(stripped)
    except ValueError:
        if re.fullmatch(r"[A-Za-z0-9_.-]+", stripped):
            return stripped
        return None


def _compare(left: float | str, operator: str, right: float | str) -> bool | None:
    if type(left) is not type(right) and not (isinstance(left, float) and isinstance(right, int)):
        return None
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if not isinstance(left, (float, int)) or not isinstance(right, (float, int)):
        return None
    return {
        ">=": left >= right,
        "<=": left <= right,
        ">": left > right,
        "<": left < right,
    }.get(operator)


def _evaluate_expression(
    expression: str, values: dict[str, FormalStateFeatureValue]
) -> tuple[FormalStateInvariantStatus, str]:
    match = _COMPARISON.fullmatch(expression.strip())
    if match is None:
        return (
            FormalStateInvariantStatus.NOT_EVALUABLE,
            "expression is outside the closed comparison grammar",
        )
    value = values.get(match.group("feature"))
    if value is None or value.state is not FormalStateMissingness.OBSERVED:
        return FormalStateInvariantStatus.NOT_EVALUABLE, "feature value is missing or unsupported"
    if value.scalar_value is not None:
        left: float | str = value.scalar_value
    elif value.category is not None:
        left = value.category
    else:
        return (
            FormalStateInvariantStatus.NOT_EVALUABLE,
            "feature representation is not scalar or categorical",
        )
    right = _literal(match.group("literal"))
    if right is None:
        return FormalStateInvariantStatus.NOT_EVALUABLE, "comparison literal is not supported"
    outcome = _compare(left, match.group("operator"), right)
    if outcome is None:
        return FormalStateInvariantStatus.NOT_EVALUABLE, "comparison types are incompatible"
    if outcome:
        return FormalStateInvariantStatus.SATISFIED, "invariant comparison satisfied"
    return FormalStateInvariantStatus.VIOLATED, "invariant comparison violated"


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M06-01 validates formal state and does not estimate this uncertainty dimension.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("No learned estimator or calibration is executed by this boundary.",),
    )


def _evidence(request: ValidateFormalProteinStateRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0601_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(request: ValidateFormalProteinStateRequest, request_hash: str) -> ProvenanceRecord:
    references = request.context.references
    controls = (
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
                decision_id=reference.decision_id,
                state=reference.state.value,
                policy_version=reference.policy_version,
                evidence_digest=reference.evidence.digest,
            )
            for role, reference in (
                (ControlRole.PROVENANCE, references.provenance),
                (ControlRole.CONSENT, references.consent),
                (ControlRole.QUALITY, references.quality),
                (ControlRole.SUPPORT, references.support),
                (ControlRole.INTENDED_USE, references.intended_use),
            )
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0601.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0601_MODULE_ID,
        module_version=M0601_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=sha256_digest(request.state_schema.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _support(status: FormalStateValidationStatus) -> SupportDecision:
    if status is FormalStateValidationStatus.VALID:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="formal_state_valid",
            rationale="All declared formal-state invariants are satisfied.",
        )
    if status is FormalStateValidationStatus.INVALID:
        return SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="formal_state_invariant_violated",
            rationale="At least one declared formal-state invariant is violated.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="formal_state_not_evaluable",
        rationale="At least one formal-state invariant cannot be evaluated safely.",
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="formal_schema_only",
            statement="M06-01 validates declared formal state and emits no biomarker panel.",
        ),
        Limitation(
            code="no_estimator_execution",
            statement=(
                "No learned, probabilistic, consensus-clustering, or treatment model is executed."
            ),
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Source artifacts and controls are caller-declared; issuer authority is not "
                "authenticated."
            ),
        ),
    )


class M0601FormalStateEngine:
    """Validate formal-state values without inference, mutation, or external I/O."""

    __slots__ = ()

    def validate(self, request: object) -> ValidateFormalProteinStateResult:
        canonical = _prepare_request(request)
        request_hash = canonical_request_digest(canonical)
        values = _value_lookup(canonical)
        invariant_results = tuple(
            FormalStateInvariantResult(
                invariant_id=invariant.invariant_id,
                status=status,
                message=message,
            )
            for invariant in canonical.state_schema.invariants
            for status, message in (_evaluate_expression(invariant.expression, values),)
        )
        statuses = {item.status for item in invariant_results}
        if FormalStateInvariantStatus.NOT_EVALUABLE in statuses or any(
            item.state is not FormalStateMissingness.OBSERVED for item in canonical.values
        ):
            validation_status = FormalStateValidationStatus.ABSTAINED
        elif FormalStateInvariantStatus.VIOLATED in statuses:
            validation_status = FormalStateValidationStatus.INVALID
        else:
            validation_status = FormalStateValidationStatus.VALID
        candidate = ValidateFormalProteinStateResult.model_construct(
            result_id=f"result.m0601.{request_hash.removeprefix('sha256:')}",
            result_version=M0601_CONTRACT_VERSION,
            request_digest=request_hash,
            result_digest=_ZERO_DIGEST,
            request=canonical,
            status=validation_status,
            support_decision=_support(validation_status),
            invariant_results=invariant_results,
            parent_target="biomarker_panel",
            emits_parent=False,
            uncertainty=_uncertainty(),
            provenance=_provenance(canonical, request_hash),
            evidence=_evidence(canonical),
            limitations=_limitations(),
        )
        payload = candidate.model_dump(mode="python")
        payload["result_digest"] = result_payload_digest(candidate)
        return ValidateFormalProteinStateResult.model_validate(payload, strict=True)


def validate_formal_protein_state(request: object) -> ValidateFormalProteinStateResult:
    """Validate one strict formal-state request through the public operation."""

    return M0601FormalStateEngine().validate(request)


__all__ = [
    "FormalStateAuthorizationError",
    "FormalStateInputError",
    "M0601FormalStateEngine",
    "preflight_formal_state_authorization",
    "validate_formal_protein_state",
]
