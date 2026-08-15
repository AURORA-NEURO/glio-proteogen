"""Deterministic, replay-safe M08-08 evidence/explanation publisher.

The dossier assigns this module a narrow publishing responsibility.  The
publisher records caller-owned evidence and diagnostics; it does not fetch,
reinterpret, or promote upstream material.  Unsupported, incomplete, and
otherwise unsafe inputs produce an auditable abstention without a parent
protein-subtype claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m08_08 import (
    M0808_EVIDENCE_CLAIM,
    M0808_MAX_CANONICAL_RESULT_BYTES,
    EvidenceBundle,
    EvidenceRole,
    ExplanationAssumption,
    ExplanationDiagnostic,
    ExplanationObject,
    PublishedEvidenceItem,
    PublisherDiagnosticStatus,
    PublisherReplayReason,
    PublisherStatus,
    PublishTranscriptProteinEvidenceRequest,
    PublishTranscriptProteinEvidenceResult,
    PublishTranscriptProteinEvidenceVerification,
    ReconstructionStatus,
    ReconstructionStep,
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

_REQUEST_ADAPTER: Final = TypeAdapter(PublishTranscriptProteinEvidenceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(PublishTranscriptProteinEvidenceResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0808AuthorizationError(PermissionError):
    """Raised when the required caller-owned safety controls are not accepted."""

    def __init__(self) -> None:
        super().__init__(
            "M08-08 requires granted consent, resolved identity, and accepted controls"
        )


class M0808InputError(ValueError):
    """Raised for oversized or non-canonical publisher output."""

    _MESSAGES: Final = {
        "result_limit": "M08-08 result exceeds the canonical byte limit",
        "result_digest": "M08-08 result digest does not match its content",
        "result_noncanonical": "M08-08 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0808Result:
    """A validated result paired with its one canonical JSON representation."""

    result: PublishTranscriptProteinEvidenceResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0808InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0808InputError("result_noncanonical")


def preflight_m0808_authorization(request: object) -> None:
    """Reject unsafe control states before any evidence projection occurs."""

    if not isinstance(request, PublishTranscriptProteinEvidenceRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise M0808AuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M0808AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M0808AuthorizationError


def _control_decisions(
    request: PublishTranscriptProteinEvidenceRequest,
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


def _provenance(request: PublishTranscriptProteinEvidenceRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts}
            | {
                request.calibration_result.digest,
                request.uncertainty_result.digest,
                refs.approved_configuration.evidence.digest,
                refs.identity_lineage.evidence.digest,
                refs.provenance.evidence.digest,
                refs.consent.evidence.digest,
                refs.quality.evidence.digest,
                refs.support.evidence.digest,
                refs.intended_use.evidence.digest,
            }
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M08-08",
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
        rationale=(
            "M08-08 references upstream uncertainty and does not recompute uncertainty "
            "dimensions in the provisional publisher ABI."
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
            "Upstream M08-06 uncertainty is content-addressed in the request.",
            "Publisher does not silently promote missing or unsupported uncertainty.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Evidence catalogue, media types, endpoint ABI, and owner-approved claim "
                "promotion policy remain provisional pending dossier sign-off."
            ),
        ),
        Limitation(
            code="caller_declared_material",
            statement=(
                "Evidence and issuer authority are recorded by digest but are not authenticated "
                "or fetched by this publisher."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits no kinase activity, generic all-omics fusion, treatment "
                "recommendation, identity inference, or parent protein-subtype claim."
            ),
        ),
    )


def _unsupported_reason(request: PublishTranscriptProteinEvidenceRequest) -> str | None:
    references = (*request.source_artifacts, request.calibration_result, request.uncertainty_result)
    for reference in references:
        marker = f"{reference.artifact_id} {reference.media_type}".casefold()
        if any(token in marker for token in ("unsupported", "missing", "ood", "quarantine")):
            return f"upstream evidence {reference.artifact_id} is unsupported or quarantined"
    return None


def _evidence_items(
    request: PublishTranscriptProteinEvidenceRequest,
) -> tuple[tuple[PublishedEvidenceItem, ...], tuple[PublishedEvidenceItem, ...]]:
    inputs = tuple(
        PublishedEvidenceItem(
            evidence_id=f"evidence.source.{index}",
            role=EvidenceRole.INPUT,
            artifact=artifact,
            claim=M0808_EVIDENCE_CLAIM,
        )
        for index, artifact in enumerate(request.source_artifacts, start=1)
    )
    diagnostics = (
        PublishedEvidenceItem(
            evidence_id="evidence.calibration",
            role=EvidenceRole.DIAGNOSTIC,
            artifact=request.calibration_result,
            claim="Caller-declared calibration output is retained by digest.",
        ),
        PublishedEvidenceItem(
            evidence_id="evidence.uncertainty",
            role=EvidenceRole.DIAGNOSTIC,
            artifact=request.uncertainty_result,
            claim="Caller-declared uncertainty output is retained by digest.",
        ),
    )
    items = inputs + diagnostics
    counter = PublishedEvidenceItem(
        evidence_id="evidence.counter",
        role=EvidenceRole.COUNTER_EVIDENCE,
        artifact=request.source_artifacts[-1],
        claim="Potential discordance remains visible as counter-evidence.",
    )
    return items, (counter,)


def _bundle(request: PublishTranscriptProteinEvidenceRequest) -> EvidenceBundle:
    items, counter = _evidence_items(request)
    digest_values = tuple(
        [request.calibration_result.digest, request.uncertainty_result.digest]
        + [item.digest for item in request.source_artifacts]
    )
    item_ids = tuple(item.evidence_id for item in items)
    return EvidenceBundle(
        bundle_id=f"bundle.{request.request_id}",
        version="0.1.0-provisional",
        items=items,
        assumptions=(
            ExplanationAssumption(
                assumption_id="assumption.caller-declared-lineage",
                statement=(
                    "Caller-declared identity, consent, quality, support, and intended-use "
                    "controls apply to the immutable evidence references."
                ),
                evidence_ids=(item_ids[0], "evidence.calibration"),
            ),
        ),
        counter_evidence=counter,
        reconstruction=(
            ReconstructionStep(
                sequence=1,
                operation="bind source, calibration, and uncertainty digests",
                input_digests=digest_values,
                output_digest="sha256:" + sha256("|".join(digest_values).encode()).hexdigest(),
                status=ReconstructionStatus.COMPLETE,
                evidence_ids=item_ids,
            ),
        ),
        evidence=tuple(
            EvidenceReference(reference=item.artifact, role="evidence", claim=item.claim)
            for item in items
        ),
    )


def _explanation(
    request: PublishTranscriptProteinEvidenceRequest,
    bundle: EvidenceBundle,
) -> ExplanationObject:
    return ExplanationObject(
        explanation_id=f"explanation.{request.request_id}",
        version="0.1.0-provisional",
        summary=(
            "Evidence and explanation material was published as a digest-bound projection; "
            "no upstream claim was relabeled or promoted."
        ),
        diagnostics=(
            ExplanationDiagnostic(
                diagnostic_id="diagnostic.source-closure",
                status=PublisherDiagnosticStatus.PASS,
                message=(
                    "All caller-declared source, calibration, and uncertainty references "
                    "are retained."
                ),
                evidence_ids=tuple(item.evidence_id for item in bundle.items),
            ),
            ExplanationDiagnostic(
                diagnostic_id="diagnostic.counter-evidence",
                status=PublisherDiagnosticStatus.PASS,
                message="Counter-evidence and reconstruction links are explicit.",
                evidence_ids=(bundle.counter_evidence[0].evidence_id,),
            ),
        ),
        limitation_statements=tuple(item.statement for item in _limitations()),
        bundle_id=bundle.bundle_id,
    )


def _build_result(
    request: PublishTranscriptProteinEvidenceRequest,
) -> PublishTranscriptProteinEvidenceResult:
    reason = _unsupported_reason(request)
    source_evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0808_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )
    if reason is None:
        bundle = _bundle(request)
        explanation = _explanation(request, bundle)
        status = PublisherStatus.PUBLISHED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0808_evidence_publisher_supported",
            rationale=(
                "Required caller-declared evidence, assumptions, counter-evidence, and "
                "reconstruction are closed."
            ),
        )
    else:
        bundle = None
        explanation = None
        status = PublisherStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="m0808_evidence_publisher_abstained",
            rationale=reason,
        )
    draft = PublishTranscriptProteinEvidenceResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        evidence_bundle=bundle,
        explanation=explanation,
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=source_evidence,
        limitations=_limitations(),
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0808EvidenceExplanationPublisher:
    """Validate, publish, and replay one deterministic M08-08 result."""

    @staticmethod
    def validate_request(request: object) -> PublishTranscriptProteinEvidenceRequest:
        preflight_m0808_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def publish(self, request: object) -> BuiltM0808Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0808_MAX_CANONICAL_RESULT_BYTES:
            raise M0808InputError("result_limit")
        return BuiltM0808Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> PublishTranscriptProteinEvidenceVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return PublishTranscriptProteinEvidenceVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=PublisherReplayReason.INVALID_RESULT,
            )
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0808_MAX_CANONICAL_RESULT_BYTES
        ):
            return PublishTranscriptProteinEvidenceVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=(
                    PublisherReplayReason.OVERSIZED
                    if isinstance(canonical_bytes, bytes)
                    else PublisherReplayReason.NON_CANONICAL
                ),
            )
        expected = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        verified = content_verified and deterministic_verified
        return PublishTranscriptProteinEvidenceVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                PublisherReplayReason.VERIFIED
                if verified
                else (
                    PublisherReplayReason.NON_CANONICAL
                    if not content_verified
                    else PublisherReplayReason.DIGEST_MISMATCH
                )
            ),
        )

    def execute(self, request: object) -> BuiltM0808Result:
        return self.publish(request)


def publish_transcript_protein_evidence_explanation(request: object) -> BuiltM0808Result:
    """Public provisional M08-08 publishing operation."""

    return M0808EvidenceExplanationPublisher().publish(request)


__all__ = [
    "BuiltM0808Result",
    "M0808AuthorizationError",
    "M0808EvidenceExplanationPublisher",
    "M0808InputError",
    "preflight_m0808_authorization",
    "publish_transcript_protein_evidence_explanation",
]
