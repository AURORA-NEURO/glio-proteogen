"""Deterministic leakage-safe representation construction runtime."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_02 import (
    M0702_EVIDENCE_CLAIM,
    M0702_MAX_CANONICAL_RESULT_BYTES,
    ConstructProteotypeAnalysisRepresentationRequest,
    ConstructProteotypeAnalysisRepresentationVerification,
    FeatureSpecification,
    LeakageCheck,
    LeakageCheckStatus,
    ProteotypeAnalysisRepresentationResult,
    RepresentationConstructionStatus,
    RepresentationFeature,
    RepresentationReplayReason,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructProteotypeAnalysisRepresentationRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeAnalysisRepresentationResult)
_LEAKAGE_TOKENS: Final = frozenset({"future", "outcome", "target", "label", "held_out"})


class RepresentationAuthorizationError(PermissionError):
    """Raised before an unauthorized request traverses source metadata."""

    def __init__(self) -> None:
        super().__init__("M07-02 representation request is not authorized")


class RepresentationInputError(ValueError):
    """Raised for malformed, oversized, or non-canonical representations."""

    _MESSAGES: Final = {
        "result_limit": "representation result exceeds byte limit",
        "result_digest": "representation result digest does not match",
        "result_noncanonical": "representation result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltRepresentation:
    """Typed result and its only canonical byte representation."""

    result: ProteotypeAnalysisRepresentationResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise RepresentationInputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise RepresentationInputError("result_noncanonical")


def preflight_representation_authorization(request: object) -> None:
    """Apply shared consent, identity, and accepted-control gates."""

    if not isinstance(request, ConstructProteotypeAnalysisRepresentationRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise RepresentationAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise RepresentationAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise RepresentationAuthorizationError


def _control_decisions(
    request: ConstructProteotypeAnalysisRepresentationRequest,
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


def _provenance(request: ConstructProteotypeAnalysisRepresentationRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {artifact.digest for artifact in request.source_artifacts}
            | {request.formal_state_result.digest}
            | {request.policy.evidence[0].reference.digest}
            if request.policy.evidence
            else {artifact.digest for artifact in request.source_artifacts}
            | {request.formal_state_result.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M07-02",
        module_version="0.1.0-provisional",
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
        rationale="Provisional constructor has no locked uncertainty estimator.",
    )
    return UncertaintyProfile(
        measurement=not_estimable,
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=not_estimable,
        transport=not_estimable,
        sensitivity_notes=("M07-02 uncertainty estimator remains provisional.",),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Feature catalogue, transform vocabulary, limits, and endpoints remain provisional."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This runtime constructs an analysis representation and emits no parent "
                "proteotype claim."
            ),
        ),
        Limitation(
            code="no_kinase_activity",
            statement="KINOPHOS owns kinase activity; M07-02 never emits it.",
        ),
        Limitation(
            code="synthetic_constructor",
            statement=(
                "Values are deterministic provisional constructor values until an owner-approved "
                "estimator is supplied."
            ),
        ),
    )


def _leakage_reason(spec: FeatureSpecification) -> str | None:
    fields = {field.casefold() for field in spec.lineage.source_fields}
    tokens = {token for field in fields for token in field.replace("-", "_").split("_")}
    if tokens & _LEAKAGE_TOKENS:
        return "feature lineage references a future, outcome, target, label, or held-out field"
    if any(not transform.leakage_safe for transform in spec.lineage.transformations):
        return "feature lineage contains a leakage-unsafe transformation"
    return None


def _feature_values(
    spec: FeatureSpecification,
    request: ConstructProteotypeAnalysisRepresentationRequest,
) -> tuple[float, ...]:
    seed = "|".join(
        [
            spec.feature_id,
            request.formal_state_result.digest,
            *sorted(artifact.digest for artifact in request.source_artifacts),
            *spec.lineage.source_fields,
            *[transform.parameters_digest for transform in spec.lineage.transformations],
        ]
    ).encode("utf-8")
    values: list[float] = []
    for index in range(spec.dimension):
        digest = sha256(seed + index.to_bytes(4, "big")).digest()
        raw = int.from_bytes(digest[:8], "big") / float(2**64)
        values.append(round((raw * 2.0) - 1.0, 8))
    return tuple(values)


def _build_result(
    request: ConstructProteotypeAnalysisRepresentationRequest,
) -> ProteotypeAnalysisRepresentationResult:
    duplicate_sources = len({item.artifact_id for item in request.source_artifacts}) != len(
        request.source_artifacts
    )
    checks: list[LeakageCheck] = []
    features: list[RepresentationFeature] = []
    failure_reasons: list[str] = []
    for spec in request.feature_specs:
        leakage_reason = _leakage_reason(spec)
        leakage_status = (
            LeakageCheckStatus.FAILED if leakage_reason else LeakageCheckStatus.PASSED
        )
        checks.append(
            LeakageCheck(
                check_id=f"leakage.{spec.feature_id}",
                status=leakage_status,
                message=(
                    leakage_reason
                    or "lineage and transformations pass provisional leakage checks"
                ),
                held_out_group=(spec.feature_id if leakage_reason else None),
            )
        )
        if leakage_reason:
            failure_reasons.append(leakage_reason)
            continue
        features.append(
            RepresentationFeature(
                feature_id=spec.feature_id,
                value_kind=spec.value_kind,
                unit=spec.unit,
                values=_feature_values(spec, request),
                mask=(True,) * spec.dimension if spec.value_kind.value == "mask" else (),
                lineage=spec.lineage,
            )
        )
    if duplicate_sources:
        failure_reasons.append("source artifact identifiers must be unique")
    constructed = not failure_reasons and len(features) == len(request.feature_specs)
    construction_status = (
        RepresentationConstructionStatus.CONSTRUCTED
        if constructed
        else RepresentationConstructionStatus.ABSTAINED
    )
    reason = None if constructed else "; ".join(dict.fromkeys(failure_reasons))
    support_status = SupportStatus.SUPPORTED if constructed else SupportStatus.REVIEW_REQUIRED
    support = SupportDecision(
        status=support_status,
        reason_code="representation_support_state",
        rationale=(
            "all feature lineage and leakage-safe construction gates are satisfied"
            if constructed
            else reason or "representation construction requires review"
        ),
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0702_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    ) + request.policy.evidence
    draft = ProteotypeAnalysisRepresentationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=construction_status,
        features=tuple(features) if constructed else (),
        leakage_checks=tuple(checks),
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return ProteotypeAnalysisRepresentationResult.model_validate(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


class M0702RepresentationEngine:
    """Build, replay, and verify one deterministic representation."""

    @staticmethod
    def validate_request(request: object) -> ConstructProteotypeAnalysisRepresentationRequest:
        preflight_representation_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def construct(self, request: object) -> BuiltRepresentation:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0702_MAX_CANONICAL_RESULT_BYTES:
            raise RepresentationInputError("result_limit")
        return BuiltRepresentation(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ConstructProteotypeAnalysisRepresentationVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return ConstructProteotypeAnalysisRepresentationVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=RepresentationReplayReason.INVALID_RESULT,
            )
        digest_verified = typed.result_digest == result_payload_digest(typed)
        try:
            replayed = self.construct(typed.request)
        except Exception:  # noqa: BLE001 - verification fails closed on replay errors.
            deterministic_verified = False
        else:
            deterministic_verified = digest_verified and (
                replayed.result.model_dump(mode="json") == typed.model_dump(mode="json")
            )
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0702_MAX_CANONICAL_RESULT_BYTES
        ):
            content_verified = False
        verified = content_verified and deterministic_verified
        return ConstructProteotypeAnalysisRepresentationVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                RepresentationReplayReason.VERIFIED
                if verified
                else RepresentationReplayReason.DIGEST_MISMATCH
            ),
        )

    def execute(self, request: object) -> BuiltRepresentation:
        return self.construct(request)


def construct_proteotype_analysis_representation(request: object) -> BuiltRepresentation:
    """Construct one representation through the stateless default engine."""

    return M0702RepresentationEngine().construct(request)


__all__ = [
    "BuiltRepresentation",
    "M0702RepresentationEngine",
    "RepresentationAuthorizationError",
    "RepresentationInputError",
    "construct_proteotype_analysis_representation",
    "preflight_representation_authorization",
]
