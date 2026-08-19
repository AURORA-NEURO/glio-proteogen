"""Deterministic, leakage-safe M06-02 representation constructor.

The dossier describes the representation boundary but does not freeze a learned
feature catalogue. This provisional runtime therefore performs only declared,
caller-owned feature construction: it preserves values, records lineage, emits
explicit masks for non-observed features, and abstains whenever support is not
demonstrated. No model weights, private data, or signer authority live here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m06_02 import (
    M0602_EVIDENCE_CLAIM,
    M0602_MAX_CANONICAL_RESULT_BYTES,
    BuildProteinRepresentationRequest,
    ConstructProteinRepresentationResult,
    ConstructProteinRepresentationVerification,
    RepresentationConstructorStatus,
    RepresentationMask,
    RepresentationObservationState,
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

_REQUEST_ADAPTER: Final = TypeAdapter(BuildProteinRepresentationRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ConstructProteinRepresentationResult)


class RepresentationAuthorizationError(PermissionError):
    """Raised before an unauthorized representation request traverses inputs."""

    def __init__(self) -> None:
        super().__init__("M06-02 representation request is not authorized")


class RepresentationInputError(ValueError):
    """Raised for malformed or unsupported representation inputs."""

    _MESSAGES: Final = {
        "result_bytes": "representation result bytes are invalid",
        "result_limit": "representation result exceeds byte limit",
        "result_digest": "representation result digest does not match",
        "result_noncanonical": "representation result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltProteinRepresentation:
    """Typed result plus its sole canonical JSON byte representation."""

    result: ConstructProteinRepresentationResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise RepresentationInputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise RepresentationInputError("result_noncanonical")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_representation_authorization(request: object) -> None:
    """Apply authorization before strict validation for typed or mapping requests."""

    if not isinstance(request, (BuildProteinRepresentationRequest, Mapping)):
        return
    expected = {
        "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
        "identity_lineage": IdentityLineageState.RESOLVED.value,
        "provenance": UpstreamDecisionState.ACCEPTED.value,
        "consent": ConsentState.GRANTED.value,
        "quality": UpstreamDecisionState.ACCEPTED.value,
        "support": UpstreamDecisionState.ACCEPTED.value,
        "intended_use": UpstreamDecisionState.ACCEPTED.value,
    }
    try:
        context = _member(request, "context")
        refs = _member(context, "references")
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise RepresentationAuthorizationError from None
    if states != expected:
        raise RepresentationAuthorizationError


def _control_decisions(
    request: BuildProteinRepresentationRequest,
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


def _provenance(request: BuildProteinRepresentationRequest) -> ProvenanceRecord:
    refs = request.context.references
    digests = (
        {item.digest for item in request.source_artifacts}
        | {item.source_digest for item in request.features}
        | {digest for step in request.lineage for digest in step.input_digests}
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M06-02",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(digests)),
        configuration_digest=request.configuration_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: BuildProteinRepresentationRequest) -> tuple[EvidenceReference, ...]:
    source = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0602_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )
    lineage = tuple(evidence for step in request.lineage for evidence in step.evidence)
    return source + lineage


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement="M06-02 field names, limits and feature catalogue remain provisional.",
        ),
        Limitation(
            code="caller_values_preserved",
            statement="No learned estimator or biological inference is executed by this seam.",
        ),
        Limitation(
            code="no_kinase_ownership",
            statement="The representation does not infer or own kinase activity.",
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Calibration and cohort support are not frozen in the provisional ABI.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Explicit abstention is required until support is established.",),
    )


def _masks(request: BuildProteinRepresentationRequest) -> tuple[RepresentationMask, ...]:
    by_feature = {item.feature_id: item for item in request.masks}
    for feature in request.features:
        if feature.state is not RepresentationObservationState.OBSERVED:
            by_feature.setdefault(
                feature.feature_id,
                RepresentationMask(
                    feature_id=feature.feature_id,
                    state=feature.state,
                    reason="caller-declared feature state is not observed",
                ),
            )
    return tuple(sorted(by_feature.values(), key=lambda item: item.feature_id))


def _support_status(
    request: BuildProteinRepresentationRequest,
) -> tuple[RepresentationConstructorStatus, SupportStatus, str]:
    states = {feature.state for feature in request.features}
    if RepresentationObservationState.UNSUPPORTED in states:
        return (
            RepresentationConstructorStatus.ABSTAINED,
            SupportStatus.UNSUPPORTED,
            "one or more features are explicitly unsupported",
        )
    if states - {RepresentationObservationState.OBSERVED}:
        return (
            RepresentationConstructorStatus.ABSTAINED,
            SupportStatus.REVIEW_REQUIRED,
            "one or more features require explicit review before interpretation",
        )
    return (
        RepresentationConstructorStatus.CONSTRUCTED,
        SupportStatus.SUPPORTED,
        "all declared features are observed and support controls are accepted",
    )


def _build_result(
    request: BuildProteinRepresentationRequest,
) -> ConstructProteinRepresentationResult:
    status, support_status, rationale = _support_status(request)
    support = SupportDecision(
        status=support_status,
        reason_code="representation_support_state",
        rationale=rationale,
    )
    draft = ConstructProteinRepresentationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        status=status,
        features=request.features,
        lineage=request.lineage,
        masks=_masks(request),
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=_evidence(request),
        limitations=_limitations(),
        completed_at=request.context.occurred_at,
    )
    result = draft.model_copy(update={"result_digest": result_payload_digest(draft)})
    return ConstructProteinRepresentationResult.model_validate(result, strict=True)


class M0602RepresentationEngine:
    """Build, replay and verify one deterministic representation result."""

    @staticmethod
    def validate_request(request: object) -> BuildProteinRepresentationRequest:
        preflight_representation_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def construct(self, request: object) -> BuiltProteinRepresentation:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0602_MAX_CANONICAL_RESULT_BYTES:
            raise RepresentationInputError("result_limit")
        return BuiltProteinRepresentation(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ConstructProteinRepresentationVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return ConstructProteinRepresentationVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=RepresentationReplayReason.INVALID_RESULT,
            )
        expected_digest = result_payload_digest(typed)
        deterministic_verified = typed.result_digest == expected_digest
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0602_MAX_CANONICAL_RESULT_BYTES
        ):
            content_verified = False
        verified = content_verified and deterministic_verified
        return ConstructProteinRepresentationVerification(
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

    def execute(self, request: object) -> BuiltProteinRepresentation:
        return self.construct(request)


def construct_protein_representation(request: object) -> BuiltProteinRepresentation:
    """Construct one result through the default stateless engine."""

    return M0602RepresentationEngine().construct(request)


__all__ = [
    "BuiltProteinRepresentation",
    "M0602RepresentationEngine",
    "RepresentationAuthorizationError",
    "RepresentationInputError",
    "construct_protein_representation",
    "preflight_representation_authorization",
]
