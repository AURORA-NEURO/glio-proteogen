"""Fail-closed, deterministic M10-08 evidence publication runtime."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final, cast

from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m10_08 import (
    M1008_CONTRACT_VERSION,
    M1008_PARENT,
    EvidencePublicationStatus,
    ProteinRnaEvidenceBundle,
    ProteinRnaEvidencePublicationResult,
    ProteinRnaExplanation,
    PublisherDiagnostic,
    PublisherDiagnosticStatus,
    PublisherFindingCode,
    PublishProteinRnaEvidenceRequest,
    ReconstructionStatus,
    canonical_request_digest,
    expected_limitations,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
)

_AUTHORIZATION_MESSAGE: Final = "M10-08 publication requires accepted upstream controls"
_EXPECTED_CONTROL_STATES: Final[dict[str, str]] = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_REQUIRED_SOURCE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "mass_spectrometry_proteome",
        "genome_transcriptome",
        "ptm_annotations",
        "upstream_protein_rna_discordance",
    }
)


class M1008AuthorizationError(PermissionError):
    """Raised when an upstream control is not in its exact accepted state."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M1008EvidencePublisherEngine:
    """Publish only a closed, caller-attributed evidence envelope."""

    __slots__ = ()

    def publish(self, request: object) -> ProteinRnaEvidencePublicationResult:
        typed = _validate_authorized_request(request)
        return _publish(typed)


def publish_protein_rna_evidence(
    request: object,
) -> ProteinRnaEvidencePublicationResult:
    """Run the stateless M10-08 publication operation."""

    return M1008EvidencePublisherEngine().publish(request)


def preflight_m1008_authorization(candidate: object) -> None:
    """Read only the seven control states and fail closed before evidence access."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROL_STATES
        }
    except Exception:  # noqa: BLE001 - hostile objects must fail closed.
        raise M1008AuthorizationError from None
    if states != _EXPECTED_CONTROL_STATES:
        raise M1008AuthorizationError


def _validate_authorized_request(candidate: object) -> PublishProteinRnaEvidenceRequest:
    preflight_m1008_authorization(candidate)
    if type(candidate) is PublishProteinRnaEvidenceRequest:
        return candidate
    if type(candidate) is dict:
        try:
            return PublishProteinRnaEvidenceRequest.model_validate(candidate, strict=True)
        except ValidationError as error:
            raise _InvalidRequestError from error
    raise _InvalidRequestTypeError


class _InvalidRequestError(ValueError):
    def __init__(self) -> None:
        super().__init__("request does not match the M10-08 contract")


class _InvalidRequestTypeError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-08 request must be a typed request or plain object")


def _validate_json_authorized_request(
    serialized: bytes | bytearray | str,
    decoded: object,
) -> PublishProteinRnaEvidenceRequest:
    """Validate a duplicate-free JSON document with JSON-native strict parsing."""

    preflight_m1008_authorization(decoded)
    try:
        return PublishProteinRnaEvidenceRequest.model_validate_json(serialized, strict=True)
    except ValidationError as error:
        raise _InvalidRequestError from error


def _publish(request: PublishProteinRnaEvidenceRequest) -> ProteinRnaEvidencePublicationResult:
    request_digest = _request_digest(request)
    input_digests = _input_digests(request)
    provenance = expected_provenance(request.context, input_digests=input_digests)
    closure = _closure_findings(request)
    if closure:
        return _abstained_result(request, request_digest, provenance, closure)
    return _published_result(request, request_digest, provenance)


def _published_result(
    request: PublishProteinRnaEvidenceRequest,
    request_digest: str,
    provenance: ProvenanceRecord,
) -> ProteinRnaEvidencePublicationResult:
    evidence = _evidence_index(request)
    bundle_id = f"bundle.m1008.{request_digest.removeprefix('sha256:')}"
    bundle = ProteinRnaEvidenceBundle(
        bundle_id=bundle_id,
        version=M1008_CONTRACT_VERSION,
        upstream_result=request.upstream_result,
        sources=request.source_artifacts,
        assumptions=request.assumptions,
        counter_evidence=request.counter_evidence,
        uncertainty=expected_uncertainty(),
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="closed_evidence_envelope",
            rationale=(
                "The caller supplied all required attribution and reconstruction fields; "
                "this does not authenticate or promote a scientific claim."
            ),
        ),
        reconstruction_status=ReconstructionStatus.COMPLETE,
        reconstruction_steps=request.reconstruction_steps,
        provenance=provenance,
        evidence=evidence,
    )
    diagnostics = (
        PublisherDiagnostic(
            diagnostic_id="diagnostic.m1008.abi",
            status=PublisherDiagnosticStatus.WARNING,
            message="ABI remains provisional and requires owner review before release.",
            evidence=evidence,
        ),
        PublisherDiagnostic(
            diagnostic_id="diagnostic.m1008.reconstruction",
            status=PublisherDiagnosticStatus.PASS,
            message="All caller-declared reconstruction steps are present and ordered.",
            evidence=evidence,
        ),
    )
    explanation = ProteinRnaExplanation(
        explanation_id=f"explanation.m1008.{request_digest.removeprefix('sha256:')}",
        version=M1008_CONTRACT_VERSION,
        bundle_id=bundle_id,
        summary=(
            "A versioned, caller-attributed evidence bundle was structurally published for "
            "protein-RNA discordance; no upstream fact was mutated or scientifically inferred."
        ),
        diagnostics=diagnostics,
        assumptions=tuple(item.assumption_id for item in request.assumptions),
        counter_evidence=tuple(item.counter_evidence_id for item in request.counter_evidence),
        reconstruction_evidence=evidence,
    )
    return _assemble_result(
        request=request,
        request_digest=request_digest,
        provenance=provenance,
        status=EvidencePublicationStatus.PUBLISHED,
        bundle=bundle,
        explanation=explanation,
        findings=(PublisherFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,),
        abstention_reason=None,
        support_decision=bundle.support_decision,
        evidence=evidence,
        human_review_required=True,
    )


def _abstained_result(
    request: PublishProteinRnaEvidenceRequest,
    request_digest: str,
    provenance: ProvenanceRecord,
    codes: tuple[PublisherFindingCode, ...],
) -> ProteinRnaEvidencePublicationResult:
    support = SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="publication_closure_incomplete",
        rationale=(
            "The publisher did not emit an evidence bundle because required closure "
            "fields are missing."
        ),
    )
    return _assemble_result(
        request=request,
        request_digest=request_digest,
        provenance=provenance,
        status=EvidencePublicationStatus.ABSTAINED,
        bundle=None,
        explanation=None,
        findings=(*codes, PublisherFindingCode.PROVISIONAL_ABI_PENDING_REVIEW),
        abstention_reason=(
            "Evidence publication abstained until attribution and reconstruction are complete."
        ),
        support_decision=support,
        evidence=_evidence_index(request),
        human_review_required=True,
    )


def _assemble_result(  # noqa: PLR0913
    *,
    request: PublishProteinRnaEvidenceRequest,
    request_digest: str,
    provenance: ProvenanceRecord,
    status: EvidencePublicationStatus,
    bundle: ProteinRnaEvidenceBundle | None,
    explanation: ProteinRnaExplanation | None,
    findings: tuple[PublisherFindingCode, ...],
    abstention_reason: str | None,
    support_decision: SupportDecision,
    evidence: tuple[EvidenceReference, ...],
    human_review_required: bool,
) -> ProteinRnaEvidencePublicationResult:
    payload: dict[str, object] = {
        "output_type": "protein_rna_evidence_explanation_publication",
        "result_id": f"result.m1008.{request_digest.removeprefix('sha256:')}",
        "result_version": M1008_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": "sha256:" + ("0" * 64),
        "request": request,
        "status": status,
        "bundle": bundle,
        "explanation": explanation,
        "findings": findings,
        "abstention_reason": abstention_reason,
        "parent_target": M1008_PARENT,
        "emits_parent": False,
        "support_decision": support_decision,
        "uncertainty": expected_uncertainty(),
        "provenance": provenance,
        "evidence": evidence,
        "limitations": expected_limitations(
            published=status is EvidencePublicationStatus.PUBLISHED
        ),
        "human_review_required": human_review_required,
    }
    partial = ProteinRnaEvidencePublicationResult.model_construct(**cast("dict[str, Any]", payload))
    payload["result_digest"] = result_payload_digest(partial)
    return ProteinRnaEvidencePublicationResult.model_validate(payload, strict=True)


def _closure_findings(
    request: PublishProteinRnaEvidenceRequest,
) -> tuple[PublisherFindingCode, ...]:
    findings: list[PublisherFindingCode] = []
    kinds = {item.kind.value for item in request.source_artifacts}
    if not _REQUIRED_SOURCE_KINDS.issubset(kinds):
        findings.append(PublisherFindingCode.MISSING_ATTRIBUTION)
    if not request.assumptions:
        findings.append(PublisherFindingCode.MISSING_ATTRIBUTION)
    if not _evidence_index(request):
        findings.append(PublisherFindingCode.MISSING_ATTRIBUTION)
    if not request.counter_evidence:
        findings.append(PublisherFindingCode.COUNTER_EVIDENCE_UNRESOLVED)
    if not request.reconstruction_steps:
        findings.append(PublisherFindingCode.RECONSTRUCTION_INCOMPLETE)
    return tuple(dict.fromkeys(findings))


def _evidence_index(request: PublishProteinRnaEvidenceRequest) -> tuple[EvidenceReference, ...]:
    references = tuple(
        evidence for source in request.source_artifacts for evidence in source.evidence
    )
    return tuple(dict.fromkeys(references))


def _input_digests(request: PublishProteinRnaEvidenceRequest) -> tuple[str, ...]:
    return (
        request.upstream_result.digest,
        *(source.artifact.digest for source in request.source_artifacts),
        *(evidence.reference.digest for evidence in _evidence_index(request)),
    )


def _request_digest(request: PublishProteinRnaEvidenceRequest) -> str:
    return canonical_request_digest(request)


def verify_publication_result(result: object) -> bool:
    """Verify strict closure and deterministic replay from the embedded request.

    A result digest proves only that the envelope is internally self-consistent.
    It does not prove that the publisher would derive the same bundle, findings,
    or explanation from the request.  Re-run the pure publisher after strict
    validation so a caller cannot resign a semantically altered result.
    """

    try:
        if type(result) is ProteinRnaEvidencePublicationResult:
            typed = result
        elif type(result) is dict:
            typed = ProteinRnaEvidencePublicationResult.model_validate(result, strict=True)
        else:
            return False
        if typed.result_digest != result_payload_digest(typed):
            return False
        expected = publish_protein_rna_evidence(typed.request)
        return expected.model_dump(mode="json") == typed.model_dump(mode="json")
    except (TypeError, ValueError, ValidationError):
        return False


def _member(candidate: object, field: str) -> object:
    if type(candidate) is dict:
        return cast("dict[str, object]", candidate).get(field)
    if isinstance(candidate, BaseModel):
        return candidate.model_dump(mode="python").get(field)
    return None


def _state_text(candidate: object) -> object:
    if isinstance(candidate, StrEnum):
        return candidate.value
    if type(candidate) is str:
        return candidate
    return None


__all__ = [
    "M1008AuthorizationError",
    "M1008EvidencePublisherEngine",
    "preflight_m1008_authorization",
    "publish_protein_rna_evidence",
    "verify_publication_result",
]
