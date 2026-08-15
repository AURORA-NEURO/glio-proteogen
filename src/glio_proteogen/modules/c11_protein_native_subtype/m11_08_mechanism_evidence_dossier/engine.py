"""Fail-closed deterministic M11-08 mechanism dossier runtime."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final, cast

from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m11_08 import (
    M1108_CONTRACT_VERSION,
    M1108_PARENT,
    AssembleVariantPeptideMechanismDossierRequest,
    ClaimCeiling,
    DossierDiagnosticStatus,
    MechanismDossierDiagnostic,
    MechanismDossierFindingCode,
    MechanismDossierStatus,
    MechanismEvidenceDossier,
    MechanismEvidenceSourceKind,
    VariantPeptideMechanismDossierResult,
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

_AUTHORIZATION_MESSAGE: Final = "M11-08 dossier assembly requires accepted upstream controls"
_EXPECTED_CONTROL_STATES: Final[dict[str, str]] = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_REQUIRED_SOURCE_KINDS: Final[frozenset[MechanismEvidenceSourceKind]] = frozenset(
    {
        MechanismEvidenceSourceKind.MASS_SPECTROMETRY_PROTEOME,
        MechanismEvidenceSourceKind.GENOME_TRANSCRIPTOME,
        MechanismEvidenceSourceKind.PTM_ANNOTATIONS,
        MechanismEvidenceSourceKind.UPSTREAM_VARIANT_PEPTIDE,
        MechanismEvidenceSourceKind.QUALITY_SUPPORT,
    }
)


class M1108AuthorizationError(PermissionError):
    """Raised when an upstream control is not in its exact accepted state."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M1108MechanismEvidenceDossierEngine:
    """Assemble only a closed, caller-attributed mechanism dossier."""

    __slots__ = ()

    def assemble(self, request: object) -> VariantPeptideMechanismDossierResult:
        typed = _validate_authorized_request(request)
        return _assemble(typed)


def assemble_mechanism_dossier(
    request: object,
) -> VariantPeptideMechanismDossierResult:
    """Run the stateless M11-08 dossier operation."""

    return M1108MechanismEvidenceDossierEngine().assemble(request)


def preflight_m1108_authorization(candidate: object) -> None:
    """Read only seven control states before any evidence field is accessed."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROL_STATES
        }
    except Exception:  # noqa: BLE001 - hostile objects must fail closed.
        raise M1108AuthorizationError from None
    if states != _EXPECTED_CONTROL_STATES:
        raise M1108AuthorizationError


def _validate_authorized_request(
    candidate: object,
) -> AssembleVariantPeptideMechanismDossierRequest:
    preflight_m1108_authorization(candidate)
    if type(candidate) is AssembleVariantPeptideMechanismDossierRequest:
        return candidate
    if type(candidate) is dict:
        try:
            return AssembleVariantPeptideMechanismDossierRequest.model_validate(
                candidate, strict=True
            )
        except ValidationError as error:
            raise _InvalidRequestError from error
    raise _InvalidRequestTypeError


class _InvalidRequestError(ValueError):
    def __init__(self) -> None:
        super().__init__("request does not match the M11-08 contract")


class _InvalidRequestTypeError(TypeError):
    def __init__(self) -> None:
        super().__init__("M11-08 request must be a typed request or plain object")


def _validate_json_authorized_request(
    serialized: bytes | bytearray | str,
    decoded: object,
) -> AssembleVariantPeptideMechanismDossierRequest:
    """Validate a duplicate-free JSON document with JSON-native strict parsing."""

    preflight_m1108_authorization(decoded)
    try:
        return AssembleVariantPeptideMechanismDossierRequest.model_validate_json(
            serialized, strict=True
        )
    except ValidationError as error:
        raise _InvalidRequestError from error


def _assemble(
    request: AssembleVariantPeptideMechanismDossierRequest,
) -> VariantPeptideMechanismDossierResult:
    request_digest = canonical_request_digest(request)
    input_digests = _input_digests(request)
    provenance = expected_provenance(request.context, input_digests=input_digests)
    findings = _closure_findings(request)
    evidence = _evidence_index(request)
    if findings:
        return _abstained_result(request, request_digest, provenance, findings, evidence)
    return _ready_result(request, request_digest, provenance, evidence)


def _ready_result(
    request: AssembleVariantPeptideMechanismDossierRequest,
    request_digest: str,
    provenance: ProvenanceRecord,
    evidence: tuple[EvidenceReference, ...],
) -> VariantPeptideMechanismDossierResult:
    dossier_id = f"dossier.m1108.{request_digest.removeprefix('sha256:')}"
    dossier = MechanismEvidenceDossier(
        dossier_id=dossier_id,
        version=M1108_CONTRACT_VERSION,
        upstream_result=request.upstream_result,
        sources=request.source_artifacts,
        assumptions=request.assumptions,
        links=request.links,
        counter_evidence=request.counter_evidence,
        validation_routes=request.validation_routes,
        reconstruction_steps=request.reconstruction_steps,
        uncertainty=expected_uncertainty(reviewed=True),
        claim_ceiling=_claim_ceiling(request),
        configuration=request.configuration,
        reviewer_id=request.reviewer_id,
        evidence=evidence,
    )
    diagnostics = (
        MechanismDossierDiagnostic(
            diagnostic_id="diagnostic.m1108.abi",
            status=DossierDiagnosticStatus.WARNING,
            message="ABI remains provisional and requires owner review before release.",
            evidence=evidence,
        ),
        MechanismDossierDiagnostic(
            diagnostic_id="diagnostic.m1108.reconstruction",
            status=DossierDiagnosticStatus.PASS,
            message="The mechanism chain is ordered, linked and independently reconstructable.",
            evidence=evidence,
        ),
        MechanismDossierDiagnostic(
            diagnostic_id="diagnostic.m1108.boundary",
            status=DossierDiagnosticStatus.PASS,
            message="Claim ceiling preserves kinase, all-omics and treatment boundaries.",
            evidence=evidence,
        ),
    )
    support = SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="closed_review_ready_dossier",
        rationale=(
            "All required caller-declared sources, counter-evidence, validation routes and "
            "reconstruction links are present; no external payload was interpreted."
        ),
    )
    return _assemble_result(
        request=request,
        request_digest=request_digest,
        provenance=provenance,
        status=MechanismDossierStatus.READY,
        dossier=dossier,
        diagnostics=diagnostics,
        findings=(MechanismDossierFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,),
        abstention_reason=None,
        support_decision=support,
        evidence=evidence,
    )


def _abstained_result(
    request: AssembleVariantPeptideMechanismDossierRequest,
    request_digest: str,
    provenance: ProvenanceRecord,
    findings: tuple[MechanismDossierFindingCode, ...],
    evidence: tuple[EvidenceReference, ...],
) -> VariantPeptideMechanismDossierResult:
    diagnostics = tuple(
        MechanismDossierDiagnostic(
            diagnostic_id=f"diagnostic.m1108.{code.value}",
            status=DossierDiagnosticStatus.NOT_EVALUABLE,
            message=_finding_message(code),
            evidence=evidence,
        )
        for code in findings
    )
    support = SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="dossier_closure_incomplete",
        rationale=(
            "The assembler abstained because a required source, reconstruction link, "
            "counter-evidence item, validation route or support control is unresolved."
        ),
    )
    return _assemble_result(
        request=request,
        request_digest=request_digest,
        provenance=provenance,
        status=MechanismDossierStatus.ABSTAINED,
        dossier=None,
        diagnostics=diagnostics,
        findings=(*findings, MechanismDossierFindingCode.PROVISIONAL_ABI_PENDING_REVIEW),
        abstention_reason=(
            "Mechanism dossier assembly abstained until evidence closure and human review "
            "requirements are satisfied."
        ),
        support_decision=support,
        evidence=evidence,
    )


def _assemble_result(  # noqa: PLR0913
    *,
    request: AssembleVariantPeptideMechanismDossierRequest,
    request_digest: str,
    provenance: ProvenanceRecord,
    status: MechanismDossierStatus,
    dossier: MechanismEvidenceDossier | None,
    diagnostics: tuple[MechanismDossierDiagnostic, ...],
    findings: tuple[MechanismDossierFindingCode, ...],
    abstention_reason: str | None,
    support_decision: SupportDecision,
    evidence: tuple[EvidenceReference, ...],
) -> VariantPeptideMechanismDossierResult:
    payload: dict[str, object] = {
        "output_type": "variant_peptide_mechanism_evidence_dossier",
        "result_id": f"result.m1108.{request_digest.removeprefix('sha256:')}",
        "result_version": M1108_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": "sha256:" + ("0" * 64),
        "request": request,
        "status": status,
        "dossier": dossier,
        "diagnostics": diagnostics,
        "findings": findings,
        "abstention_reason": abstention_reason,
        "parent_target": M1108_PARENT,
        "emits_parent": False,
        "support_decision": support_decision,
        "uncertainty": expected_uncertainty(reviewed=status is MechanismDossierStatus.READY),
        "provenance": provenance,
        "evidence": evidence,
        "limitations": expected_limitations(ready=status is MechanismDossierStatus.READY),
        "human_review_required": True,
    }
    partial = VariantPeptideMechanismDossierResult.model_construct(**cast("Any", payload))
    payload["result_digest"] = result_payload_digest(partial)
    return VariantPeptideMechanismDossierResult.model_validate(payload, strict=True)


def _claim_ceiling(request: AssembleVariantPeptideMechanismDossierRequest) -> ClaimCeiling:
    return _default_claim_ceiling(request)


def _default_claim_ceiling(
    request: AssembleVariantPeptideMechanismDossierRequest,
) -> ClaimCeiling:
    evidence = _evidence_index(request)
    return ClaimCeiling(
        maximum_claim="Review-ready mechanistic association under caller-declared evidence.",
        prohibited_interpretations=(
            "No KINOPHOS kinase-state inference.",
            "No generic all-omics fusion claim.",
            "No direct treatment recommendation.",
        ),
        rationale="The dossier preserves a claim ceiling until independent review and validation.",
        evidence=evidence[:1],
    )


def _closure_findings(
    request: AssembleVariantPeptideMechanismDossierRequest,
) -> tuple[MechanismDossierFindingCode, ...]:
    findings: list[MechanismDossierFindingCode] = []
    kinds = {source.kind for source in request.source_artifacts}
    missing = _REQUIRED_SOURCE_KINDS - kinds
    if missing:
        findings.append(MechanismDossierFindingCode.MISSING_SOURCE)
    link_kinds = {link.kind.value for link in request.links}
    if "mechanism" not in link_kinds or "claim_ceiling" not in link_kinds:
        findings.append(MechanismDossierFindingCode.CHAIN_INCOMPLETE)
    if not request.counter_evidence:
        findings.append(MechanismDossierFindingCode.COUNTER_EVIDENCE_MISSING)
    if not request.validation_routes or any(
        route.status in {"failed", "not_evaluable"} for route in request.validation_routes
    ):
        findings.append(MechanismDossierFindingCode.VALIDATION_ROUTE_UNRESOLVED)
    if not request.reconstruction_steps:
        findings.append(MechanismDossierFindingCode.CHAIN_INCOMPLETE)
    return tuple(dict.fromkeys(findings))


def _finding_message(code: MechanismDossierFindingCode) -> str:
    return {
        MechanismDossierFindingCode.MISSING_SOURCE: "Required source attribution is missing.",
        MechanismDossierFindingCode.CHAIN_INCOMPLETE: (
            "The reconstructable evidence chain is incomplete."
        ),
        MechanismDossierFindingCode.COUNTER_EVIDENCE_MISSING: "Counter-evidence is not resolved.",
        MechanismDossierFindingCode.VALIDATION_ROUTE_UNRESOLVED: (
            "A validation route is unresolved."
        ),
    }.get(code, "The mechanism dossier cannot be evaluated safely.")


def _evidence_index(
    request: AssembleVariantPeptideMechanismDossierRequest,
) -> tuple[EvidenceReference, ...]:
    references: list[EvidenceReference] = []
    for source in request.source_artifacts:
        references.extend(source.evidence)
    references.extend(request.configuration.evidence)
    for link in request.links:
        references.extend(link.evidence)
    for counter in request.counter_evidence:
        references.extend(counter.evidence)
    for route in request.validation_routes:
        references.extend(route.evidence)
    return tuple(dict.fromkeys(references))


def _input_digests(request: AssembleVariantPeptideMechanismDossierRequest) -> tuple[str, ...]:
    return (
        request.upstream_result.digest,
        *(item.artifact.digest for item in request.source_artifacts),
        *(item.digest for item in request.configuration.source_manifest),
        *(item.reference.digest for item in _evidence_index(request)),
    )


def verify_mechanism_dossier_result(result: object) -> bool:
    """Verify strict model closure and the canonical replay digest."""

    try:
        typed = (
            result
            if type(result) is VariantPeptideMechanismDossierResult
            else VariantPeptideMechanismDossierResult.model_validate(result, strict=True)
        )
        return typed.result_digest == result_payload_digest(typed)
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
    "M1108AuthorizationError",
    "M1108MechanismEvidenceDossierEngine",
    "assemble_mechanism_dossier",
    "preflight_m1108_authorization",
    "verify_mechanism_dossier_result",
]
