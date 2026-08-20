"""Deterministic, lineage-complete M08-02 representation construction."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m08_02 import (
    M0802_EVIDENCE_CLAIM,
    M0802_MAX_CANONICAL_RESULT_BYTES,
    M0802_MODULE_ID,
    ConstructTranscriptProteinRepresentationRequest,
    ConstructTranscriptProteinRepresentationVerification,
    FeatureSpecification,
    LeakageCheck,
    LeakageCheckStatus,
    RepresentationConstructionStatus,
    RepresentationFeature,
    RepresentationReplayReason,
    TranscriptProteinRepresentationResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructTranscriptProteinRepresentationRequest)
_RESULT_ADAPTER: Final = TypeAdapter(TranscriptProteinRepresentationResult)
_LEAKAGE_TOKENS: Final = frozenset(
    {"future", "outcome", "target", "label", "held_out", "heldout", "response"}
)


class RepresentationAuthorizationError(PermissionError):
    """Raised before an unauthorized request reaches the constructor."""

    def __init__(self) -> None:
        super().__init__("M08-02 representation request is not authorized")


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
    """Typed result and its sole canonical byte representation."""

    result: TranscriptProteinRepresentationResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise RepresentationInputError("result_digest")
        expected = canonical_json_bytes(self.result.model_dump(mode="json"))
        if expected != self.canonical_bytes:
            raise RepresentationInputError("result_noncanonical")


def preflight_representation_authorization(request: object) -> None:
    """Apply consent, identity, and accepted-control gates without inference."""

    if not isinstance(request, ConstructTranscriptProteinRepresentationRequest):
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
    request: ConstructTranscriptProteinRepresentationRequest,
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


def _provenance(request: ConstructTranscriptProteinRepresentationRequest) -> ProvenanceRecord:
    refs = request.context.references
    policy_digests = tuple(item.reference.digest for item in request.policy.evidence)
    input_digests = tuple(
        sorted(
            {artifact.digest for artifact in request.source_artifacts}
            | {request.formal_state_result.digest}
            | set(policy_digests)
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M0802_MODULE_ID,
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
        rationale="No owner-approved M08-02 uncertainty estimator is frozen yet.",
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
            "Measurement, sampling, parameter, model-form, identification, support, "
            "and transport uncertainty remain explicitly non-estimable pending owner review.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "The feature catalogue, transform vocabulary, limits, operation, and media "
                "type are provisional dossier-derived implementation metadata."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "M08-02 constructs a versioned analysis representation and emits no protein "
                "subtype claim."
            ),
        ),
        Limitation(
            code="kinase_activity_owned_elsewhere",
            statement="KINOPHOS owns kinase-state output; M08-02 never emits kinase activity.",
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Evidence and provenance references are linked but their issuer authority is "
                "not authenticated by this constructor."
            ),
        ),
    )


def _leakage_reason(spec: FeatureSpecification) -> str | None:
    fields = {field.casefold() for field in spec.lineage.source_fields}
    tokens = {token for field in fields for token in field.replace("-", "_").split("_")}
    if tokens & _LEAKAGE_TOKENS:
        return (
            "feature lineage references a future, outcome, target, label, response, "
            "or held-out field"
        )
    if any(not item.leakage_safe for item in spec.lineage.transformations):
        return "feature lineage contains a leakage-unsafe transformation"
    return None


def _feature_values(
    spec: FeatureSpecification,
    request: ConstructTranscriptProteinRepresentationRequest,
) -> tuple[float, ...]:
    """Derive stable placeholder values without pretending to estimate biology."""

    seed = "|".join(
        (
            spec.feature_id,
            spec.version,
            request.formal_state_result.digest,
            *sorted(artifact.digest for artifact in request.source_artifacts),
            *spec.lineage.source_fields,
            *[item.parameters_digest for item in spec.lineage.transformations],
            request.policy.policy_id,
            request.policy.version,
        )
    ).encode("utf-8")
    values: list[float] = []
    for index in range(spec.dimension):
        digest = sha256(seed + index.to_bytes(4, "big")).digest()
        raw = int.from_bytes(digest[:8], "big") / float(2**64)
        values.append(round((raw * 2.0) - 1.0, 8))
    return tuple(values)


def _build_result(
    request: ConstructTranscriptProteinRepresentationRequest,
) -> TranscriptProteinRepresentationResult:
    duplicate_sources = len({item.artifact_id for item in request.source_artifacts}) != len(
        request.source_artifacts
    )
    checks: list[LeakageCheck] = []
    features: list[RepresentationFeature] = []
    failure_reasons: list[str] = []
    for spec in request.feature_specs:
        leakage_reason = _leakage_reason(spec)
        checks.append(
            LeakageCheck(
                check_id=f"leakage.{spec.feature_id}",
                status=(LeakageCheckStatus.FAILED if leakage_reason else LeakageCheckStatus.PASSED),
                message=(
                    leakage_reason
                    or "lineage, source fields, and locked transforms pass leakage checks"
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
    status = (
        RepresentationConstructionStatus.CONSTRUCTED
        if constructed
        else RepresentationConstructionStatus.ABSTAINED
    )
    reason = None if constructed else "; ".join(dict.fromkeys(failure_reasons))
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if constructed else SupportStatus.REVIEW_REQUIRED,
        reason_code="representation_support_state",
        rationale=(
            "all feature lineage and leakage-safe construction gates are satisfied"
            if constructed
            else reason or "representation construction requires human review"
        ),
    )
    evidence = (
        tuple(
            EvidenceReference(reference=item, role="evidence", claim=M0802_EVIDENCE_CLAIM)
            for item in request.source_artifacts
        )
        + request.policy.evidence
    )
    draft = TranscriptProteinRepresentationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=status,
        features=tuple(features) if constructed else (),
        leakage_checks=tuple(checks),
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return TranscriptProteinRepresentationResult.model_validate(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


class M0802RepresentationEngine:
    """Build, execute, and replay one deterministic M08-02 representation."""

    @staticmethod
    def validate_request(request: object) -> ConstructTranscriptProteinRepresentationRequest:
        preflight_representation_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def construct(self, request: object) -> BuiltRepresentation:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0802_MAX_CANONICAL_RESULT_BYTES:
            raise RepresentationInputError("result_limit")
        return BuiltRepresentation(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ConstructTranscriptProteinRepresentationVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return ConstructTranscriptProteinRepresentationVerification(
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
            or len(canonical_bytes) > M0802_MAX_CANONICAL_RESULT_BYTES
        ):
            content_verified = False
        verified = content_verified and deterministic_verified
        reason = (
            RepresentationReplayReason.VERIFIED
            if verified
            else (
                RepresentationReplayReason.CANONICAL_BYTES_MISMATCH
                if deterministic_verified
                else RepresentationReplayReason.DIGEST_MISMATCH
            )
        )
        return ConstructTranscriptProteinRepresentationVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=reason,
        )

    def execute(self, request: object) -> BuiltRepresentation:
        return self.construct(request)


def construct_transcript_protein_representation(request: object) -> BuiltRepresentation:
    """Construct one representation through the stateless default engine."""

    return M0802RepresentationEngine().construct(request)


__all__ = [
    "BuiltRepresentation",
    "M0802RepresentationEngine",
    "RepresentationAuthorizationError",
    "RepresentationInputError",
    "construct_transcript_protein_representation",
    "preflight_representation_authorization",
]
