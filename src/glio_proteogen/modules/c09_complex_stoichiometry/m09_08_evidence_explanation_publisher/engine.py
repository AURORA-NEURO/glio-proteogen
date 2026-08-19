"""Deterministic M09-08 evidence publication and replay boundary.

The dossier requires an auditable evidence bundle and explanation, but it does
not freeze a media catalogue, endpoint, or upstream ABI.  The runtime therefore
accepts only content-addressed, caller-declared references.  It never fetches,
mutates, relabels, or traverses external payloads.  Publication is allowed only
when attribution, assumptions, counter-evidence, and a complete deterministic
reconstruction chain are present; every other case is an explicit abstention.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_08 import (
    M0908_EVIDENCE_CLAIM,
    M0908_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivityEvidenceBundle,
    ComplexActivityEvidencePublicationResult,
    ComplexActivityEvidencePublicationVerification,
    ComplexActivityExplanation,
    EvidencePublicationStatus,
    PublicationReplayReason,
    PublishComplexActivityEvidenceRequest,
    PublisherDiagnostic,
    PublisherDiagnosticStatus,
    PublisherEvidenceSource,
    PublisherFindingCode,
    PublisherSourceKind,
    ReconstructionStatus,
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

_REQUEST_ADAPTER: Final = TypeAdapter(PublishComplexActivityEvidenceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityEvidencePublicationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_REQUIRED_SOURCE_KINDS: Final = frozenset(
    {
        PublisherSourceKind.MASS_SPECTROMETRY_PROTEOME,
        PublisherSourceKind.GENOME_TRANSCRIPTOME,
        PublisherSourceKind.PTM_ANNOTATIONS,
        PublisherSourceKind.UPSTREAM_COMPLEX_ACTIVITY,
        PublisherSourceKind.QUALITY_SUPPORT,
    }
)


class M0908AuthorizationError(PermissionError):
    """Raised when privacy, identity, or upstream control preflight fails."""

    def __init__(self) -> None:
        super().__init__(
            "M09-08 requires granted consent, resolved identity, and accepted controls"
        )


class M0908InputError(ValueError):
    """Raised for oversized or non-canonical publication material."""

    _MESSAGES: Final = {
        "result_limit": "M09-08 result exceeds the canonical byte limit",
        "result_digest": "M09-08 result digest does not match its content",
        "result_noncanonical": "M09-08 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0908Result:
    """Validated publication result paired with its canonical byte envelope."""

    result: ComplexActivityEvidencePublicationResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0908InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0908InputError("result_noncanonical")


def preflight_m0908_authorization(request: object) -> None:
    """Fail closed before reading source declarations or reconstruction steps."""

    if not isinstance(request, PublishComplexActivityEvidenceRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise M0908AuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M0908AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M0908AuthorizationError


def _control_decisions(
    request: PublishComplexActivityEvidenceRequest,
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


def _provenance(request: PublishComplexActivityEvidenceRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {request.upstream_result.digest}
            | {item.artifact.digest for item in request.source_artifacts}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M09-08",
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
            "M09-08 has no owner-locked uncertainty estimator in the provisional ABI; "
            "uncertainty is exposed as not estimable rather than silently omitted."
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
            "Measurement, sampling, parameter, model-form, identification, support, "
            "and transport dimensions require owner-locked calibration before release.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "The upstream M09-07 ABI, catalogue, media types, endpoint, and release "
                "policy remain provisional pending owner confirmation."
            ),
        ),
        Limitation(
            code="opaque_external_evidence",
            statement=(
                "Evidence is represented by caller-declared content-addressed references; "
                "this module does not authenticate issuers or traverse raw payloads."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The publisher emits no kinase activity, generic all-omics fusion, direct "
                "treatment recommendation, identity inference, or parent claim."
            ),
        ),
    )


def _evidence_for_source(source: object) -> EvidenceReference:
    # The source type is checked by the request adapter before this function runs.
    typed = source
    if not isinstance(typed, PublisherEvidenceSource):
        raise TypeError
    return EvidenceReference(
        reference=typed.artifact,
        role="evidence",
        claim=M0908_EVIDENCE_CLAIM,
    )


def _reconstruction_is_closed(request: PublishComplexActivityEvidenceRequest) -> bool:
    """Require a deterministic chain rooted at upstream and source digests."""

    if not request.reconstruction_steps:
        return False
    known = {request.upstream_result.digest}
    known.update(item.artifact.digest for item in request.source_artifacts)
    previous_output: str | None = None
    for step in request.reconstruction_steps:
        inputs = set(step.input_digests)
        if not inputs.issubset(known):
            return False
        if previous_output is None and request.upstream_result.digest not in inputs:
            return False
        if previous_output is not None and previous_output not in inputs:
            return False
        expected = sha256_digest(
            {
                "module": "GLIO-PROTEOGEN-M09-08",
                "sequence": step.sequence,
                "operation": step.operation,
                "input_digests": sorted(inputs),
            }
        )
        if step.output_digest != expected:
            return False
        known.add(step.output_digest)
        previous_output = step.output_digest
    return True


def _diagnostics(
    request: PublishComplexActivityEvidenceRequest,
    *,
    human_review_required: bool,
) -> tuple[PublisherDiagnostic, ...]:
    return (
        PublisherDiagnostic(
            diagnostic_id="diagnostic.attribution",
            status=PublisherDiagnosticStatus.PASS,
            message="All required source kinds are attributed by immutable references.",
        ),
        PublisherDiagnostic(
            diagnostic_id="diagnostic.assumptions",
            status=PublisherDiagnosticStatus.PASS,
            message=f"{len(request.assumptions)} caller-declared assumptions are retained.",
        ),
        PublisherDiagnostic(
            diagnostic_id="diagnostic.counter-evidence",
            status=(
                PublisherDiagnosticStatus.WARNING
                if human_review_required
                else PublisherDiagnosticStatus.PASS
            ),
            message=(
                "Counter-evidence is retained and requires human review for a critical "
                "or unresolved discrepancy."
                if human_review_required
                else "Counter-evidence is retained as an explicit reviewable section."
            ),
        ),
        PublisherDiagnostic(
            diagnostic_id="diagnostic.reconstruction",
            status=PublisherDiagnosticStatus.PASS,
            message="Every reconstruction step is digest-bound to known inputs and prior outputs.",
        ),
        PublisherDiagnostic(
            diagnostic_id="diagnostic.uncertainty",
            status=PublisherDiagnosticStatus.NOT_EVALUABLE,
            message="Owner-locked uncertainty calibration is pending; no uncertainty is hidden.",
        ),
    )


def _abstention(
    request: PublishComplexActivityEvidenceRequest,
    findings: tuple[PublisherFindingCode, ...],
    reason: str,
) -> ComplexActivityEvidencePublicationResult:
    support = SupportDecision(
        status=(
            SupportStatus.UNSUPPORTED
            if PublisherFindingCode.UPSTREAM_ABSTAINED in findings
            else SupportStatus.REVIEW_REQUIRED
        ),
        reason_code="m0908_publication_abstention",
        rationale=reason,
    )
    draft = ComplexActivityEvidencePublicationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=EvidencePublicationStatus.ABSTAINED,
        bundle=None,
        explanation=None,
        findings=findings,
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=(),
        limitations=_limitations(),
        human_review_required=True,
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


def _build_result(
    request: PublishComplexActivityEvidenceRequest,
) -> ComplexActivityEvidencePublicationResult:
    kinds = {item.kind for item in request.source_artifacts}
    missing = _REQUIRED_SOURCE_KINDS - kinds
    findings: list[PublisherFindingCode] = []
    reasons: list[str] = []
    if missing:
        findings.append(PublisherFindingCode.MISSING_ATTRIBUTION)
        reasons.append("required evidence source kinds are missing")
    if not request.assumptions:
        findings.append(PublisherFindingCode.MISSING_ATTRIBUTION)
        reasons.append("assumptions are required for publication")
    if not request.counter_evidence:
        findings.append(PublisherFindingCode.COUNTER_EVIDENCE_UNRESOLVED)
        reasons.append("counter-evidence is required for publication")
    if not _reconstruction_is_closed(request):
        findings.append(PublisherFindingCode.RECONSTRUCTION_INCOMPLETE)
        reasons.append("reconstruction chain is absent or not digest-closed")
    unique_findings = tuple(dict.fromkeys(findings))
    if len(unique_findings) > 1 or reasons:
        return _abstention(
            request,
            unique_findings,
            "; ".join(dict.fromkeys(reasons)) or "publication requires human review",
        )

    evidence = tuple(_evidence_for_source(item) for item in request.source_artifacts)
    human_review_required = any(
        marker in (item.statement + item.impact).casefold()
        for item in request.counter_evidence
        for marker in ("critical", "unresolved", "conflict", "novel", "ood")
    )
    bundle = ComplexActivityEvidenceBundle(
        bundle_id=f"bundle.{request.request_id}",
        version="0.1.0-provisional",
        upstream_result=request.upstream_result,
        sources=request.source_artifacts,
        assumptions=request.assumptions,
        counter_evidence=request.counter_evidence,
        uncertainty=_uncertainty(),
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0908_publication_supported",
            rationale=(
                "Required attribution, review sections, and reconstruction closure are present."
            ),
        ),
        reconstruction_status=ReconstructionStatus.COMPLETE,
        reconstruction_steps=request.reconstruction_steps,
        provenance=_provenance(request),
        evidence=evidence,
    )
    explanation = ComplexActivityExplanation(
        explanation_id=f"explanation.{request.request_id}",
        version="0.1.0-provisional",
        bundle_id=bundle.bundle_id,
        summary=(
            "Complex activity evidence was published with explicit attribution, assumptions, "
            "counter-evidence, uncertainty, and digest-closed reconstruction."
        ),
        diagnostics=_diagnostics(request, human_review_required=human_review_required),
        assumptions=tuple(item.assumption_id for item in request.assumptions),
        counter_evidence=tuple(item.counter_evidence_id for item in request.counter_evidence),
        reconstruction_evidence=tuple(
            item for step in request.reconstruction_steps for item in step.evidence
        )
        or evidence,
    )
    draft = ComplexActivityEvidencePublicationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=EvidencePublicationStatus.PUBLISHED,
        bundle=bundle,
        explanation=explanation,
        findings=(),
        abstention_reason=None,
        support_decision=bundle.support_decision,
        uncertainty=bundle.uncertainty,
        provenance=bundle.provenance,
        evidence=evidence,
        limitations=_limitations(),
        human_review_required=human_review_required,
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0908EvidencePublisher:
    """Build, execute, validate, and replay one M09-08 publication."""

    @staticmethod
    def validate_request(request: object) -> PublishComplexActivityEvidenceRequest:
        typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m0908_authorization(typed)
        return typed

    def publish(self, request: object) -> BuiltM0908Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0908_MAX_CANONICAL_RESULT_BYTES:
            raise M0908InputError("result_limit")
        return BuiltM0908Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ComplexActivityEvidencePublicationVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return ComplexActivityEvidencePublicationVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=PublicationReplayReason.INVALID_RESULT,
            )
        if typed.provenance != _provenance(typed.request):
            return ComplexActivityEvidencePublicationVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=PublicationReplayReason.DIGEST_MISMATCH,
            )
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0908_MAX_CANONICAL_RESULT_BYTES
        ):
            return ComplexActivityEvidencePublicationVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=(
                    PublicationReplayReason.OVERSIZED
                    if isinstance(canonical_bytes, bytes)
                    else PublicationReplayReason.NON_CANONICAL
                ),
            )
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        digest_verified = typed.result_digest == result_payload_digest(typed)
        try:
            replayed = self.publish(typed.request)
        except Exception:  # noqa: BLE001 - verification fails closed on replay errors.
            deterministic_verified = False
        else:
            deterministic_verified = digest_verified and (
                replayed.result.model_dump(mode="json") == typed.model_dump(mode="json")
            )
        verified = content_verified and deterministic_verified
        return ComplexActivityEvidencePublicationVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                PublicationReplayReason.VERIFIED
                if verified
                else (
                    PublicationReplayReason.NON_CANONICAL
                    if not content_verified
                    else PublicationReplayReason.DIGEST_MISMATCH
                )
            ),
        )

    def execute(self, request: object) -> BuiltM0908Result:
        return self.publish(request)


def publish_complex_activity_evidence(request: object) -> BuiltM0908Result:
    """Public provisional M09-08 operation."""

    return M0908EvidencePublisher().publish(request)


__all__ = [
    "BuiltM0908Result",
    "M0908AuthorizationError",
    "M0908EvidencePublisher",
    "M0908InputError",
    "preflight_m0908_authorization",
    "publish_complex_activity_evidence",
]
