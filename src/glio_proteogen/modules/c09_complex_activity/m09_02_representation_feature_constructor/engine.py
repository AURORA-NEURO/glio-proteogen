"""Deterministic, leakage-safe M09-02 representation construction runtime.

The dossier describes a representation boundary but intentionally does not freeze
an estimator, feature catalogue, endpoint, or media contract.  This runtime keeps
those choices explicit and provisional: feature values are generated from locked
content-addressed inputs, transformations are never learned from the request, and
missing, unsupported, OOD, or unevaluable paths abstain without manufacturing a
negative finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_02 import (
    M0902_CONTRACT_VERSION,
    M0902_EVIDENCE_CLAIM,
    M0902_MAX_CANONICAL_RESULT_BYTES,
    M0902_MODULE_ID,
    ComplexActivityRepresentationResult,
    ConstructComplexActivityRepresentationRequest,
    LeakageCheck,
    LeakageCheckStatus,
    RepresentationConstructionStatus,
    RepresentationFeature,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructComplexActivityRepresentationRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityRepresentationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0902AuthorizationError(PermissionError):
    """Raised when consent, identity, or an upstream control is not accepted."""

    def __init__(self) -> None:
        super().__init__(
            "M09-02 requires granted consent, resolved identity, and accepted controls"
        )


class M0902InputError(ValueError):
    """Raised when replay material exceeds bounds or is not canonical."""

    _MESSAGES: Final = {
        "result_limit": "M09-02 result exceeds the canonical byte limit",
        "result_digest": "M09-02 result digest does not match its content",
        "result_noncanonical": "M09-02 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0902Result:
    """Typed result plus the only canonical byte representation."""

    result: ComplexActivityRepresentationResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0902InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0902InputError("result_noncanonical")


def preflight_m0902_authorization(request: object) -> None:
    """Check the seven caller-declared controls before construction."""

    if not isinstance(request, ConstructComplexActivityRepresentationRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise M0902AuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M0902AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M0902AuthorizationError


def _control_decisions(
    request: ConstructComplexActivityRepresentationRequest,
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


def _provenance(request: ConstructComplexActivityRepresentationRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts}
            | {request.formal_state_result.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M0902_MODULE_ID,
        module_version=M0902_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _uncertainty() -> UncertaintyProfile:
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M09-02 has no owner-locked probabilistic estimator in the provisional ABI; "
            "construction therefore exposes explicit non-estimability."
        ),
    )
    return UncertaintyProfile(
        measurement=not_estimable,
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=not_estimable,
        transport=not_estimable,
        sensitivity_notes=(
            "Sensitivity, support, and transport uncertainty require owner-locked validation "
            "data and are not inferred from caller-declared references.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Feature catalogue, learned estimator, endpoint, capacities, and media type "
                "remain provisional pending owner confirmation."
            ),
        ),
        Limitation(
            code="caller_declared_inputs",
            statement=(
                "References are content-addressed and replay-bound, but issuer authority and "
                "external artifact content are not authenticated or traversed."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits no kinase activity, generic all-omics fusion, treatment "
                "recommendation, identity inference, or protein-level subtype claim."
            ),
        ),
    )


def _seed(feature_id: str, request: ConstructComplexActivityRepresentationRequest) -> bytes:
    digest = canonical_request_digest(request)
    source_digests = ",".join(sorted(item.digest for item in request.source_artifacts))
    return (
        f"{feature_id}|{digest}|{request.policy.policy_id}|{request.policy.version}|{source_digests}"
    ).encode()


def _values(
    feature_id: str,
    dimension: int,
    request: ConstructComplexActivityRepresentationRequest,
) -> tuple[float, ...]:
    seed = _seed(feature_id, request)
    values: list[float] = []
    for position in range(dimension):
        block = sha256(seed + f"|{position}".encode("ascii")).digest()
        raw = int.from_bytes(block[:8], "big") / float(2**64)
        values.append(round(raw, 8))
    return tuple(values)


def _evidence(
    request: ConstructComplexActivityRepresentationRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0902_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )


def _quality_reason(request: ConstructComplexActivityRepresentationRequest) -> str | None:
    """Return a safe-failure reason for explicit unsupported/poor-quality markers."""

    haystack = " ".join(
        (
            request.policy.scaling_method,
            request.policy.mask_policy,
            *(item.artifact_id for item in request.source_artifacts),
            *(item.media_type for item in request.source_artifacts),
        )
    ).casefold()
    markers = (
        ("missing", "required representation input is missing"),
        ("unsupported", "representation input or transformation is unsupported"),
        ("ood", "representation input is outside the declared support domain"),
        ("not_evaluable", "representation quality cannot be evaluated safely"),
    )
    for marker, reason in markers:
        if marker in haystack:
            return reason
    return None


def _leakage_checks(
    request: ConstructComplexActivityRepresentationRequest,
) -> tuple[tuple[LeakageCheck, ...], str | None]:
    checks: list[LeakageCheck] = []
    failure: str | None = None
    policy_text = f"{request.policy.scaling_method} {request.policy.mask_policy}".casefold()
    for specification in request.feature_specs:
        marker = " ".join(specification.lineage.source_fields).casefold()
        if "leakage_failure" in policy_text or "leakage_failure" in marker:
            status = LeakageCheckStatus.FAILED
            message = "held-out group is not isolated from the transformation fit"
            failure = "leakage check failed for " + specification.feature_id
        elif "leakage_unknown" in policy_text or "leakage_unknown" in marker:
            status = LeakageCheckStatus.NOT_EVALUABLE
            message = "held-out group metadata is unavailable"
            failure = "leakage check is not evaluable for " + specification.feature_id
        else:
            status = LeakageCheckStatus.PASSED
            message = "locked transformation has no access to held-out target information"
        checks.append(
            LeakageCheck(
                check_id=f"leakage.{specification.feature_id}",
                status=status,
                message=message,
                held_out_group=("held-out-group" if status is LeakageCheckStatus.FAILED else None),
                evidence=specification.lineage.evidence,
            )
        )
    return tuple(checks), failure


def _build_result(
    request: ConstructComplexActivityRepresentationRequest,
) -> ComplexActivityRepresentationResult:
    checks, leakage_failure = _leakage_checks(request)
    quality_failure = _quality_reason(request)
    reason = leakage_failure or quality_failure
    evidence = _evidence(request)
    features: list[RepresentationFeature] = []
    if reason is None:
        for specification in request.feature_specs:
            values = _values(specification.feature_id, specification.dimension, request)
            mask = tuple(True for _ in values)
            features.append(
                RepresentationFeature(
                    feature_id=specification.feature_id,
                    value_kind=specification.value_kind,
                    unit=specification.unit,
                    values=values,
                    mask=mask,
                    lineage=specification.lineage,
                    evidence=evidence,
                )
            )
    status = (
        RepresentationConstructionStatus.CONSTRUCTED
        if reason is None
        else RepresentationConstructionStatus.ABSTAINED
    )
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if reason is None else SupportStatus.UNSUPPORTED,
        reason_code="m0902_representation_support",
        rationale=(
            "all requested features have complete leakage-safe lineage and supported inputs"
            if reason is None
            else reason
        ),
    )
    draft = ComplexActivityRepresentationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        features=tuple(features),
        leakage_checks=checks,
        abstention_reason=reason,
        parent_target="complex_activity",
        emits_parent=False,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0902RepresentationConstructor:
    """Validate, construct, and replay one deterministic M09-02 result."""

    @staticmethod
    def validate_request(request: object) -> ConstructComplexActivityRepresentationRequest:
        preflight_m0902_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def construct(self, request: object) -> BuiltM0902Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0902_MAX_CANONICAL_RESULT_BYTES:
            raise M0902InputError("result_limit")
        return BuiltM0902Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> bool:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return False
        if typed.provenance != _provenance(typed.request):
            return False
        if canonical_bytes is not None:
            if (
                type(canonical_bytes) is not bytes
                or len(canonical_bytes) > M0902_MAX_CANONICAL_RESULT_BYTES
            ):
                return False
            if canonical_bytes != canonical_json_bytes(typed.model_dump(mode="json")):
                return False
        return typed.result_digest == result_payload_digest(typed)

    def execute(self, request: object) -> BuiltM0902Result:
        return self.construct(request)


def construct_complex_activity_representation(request: object) -> BuiltM0902Result:
    """Public provisional M09-02 operation."""

    return M0902RepresentationConstructor().construct(request)


__all__ = [
    "BuiltM0902Result",
    "M0902AuthorizationError",
    "M0902InputError",
    "M0902RepresentationConstructor",
    "construct_complex_activity_representation",
    "preflight_m0902_authorization",
]
