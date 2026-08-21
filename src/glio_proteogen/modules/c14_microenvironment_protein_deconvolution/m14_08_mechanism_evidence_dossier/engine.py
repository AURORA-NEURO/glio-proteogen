"""Deterministic, replay-bound M14-08 evidence dossier runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_08 import (
    M1408_CONTRACT_VERSION,
    M1408_EVIDENCE_CLAIM,
    M1408_PARENT,
    DossierFinding,
    DossierFindingCode,
    DossierStatus,
    EvidenceDisposition,
    MechanismEvidenceDossier,
    ProteinSubtypeMechanismEvidenceDossierResult,
    PublishProteinSubtypeMechanismDossierRequest,
    ValidationRouteStatus,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m14_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(PublishProteinSubtypeMechanismDossierRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeMechanismEvidenceDossierResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_METHODS: Final = frozenset(
    {
        "evidence_graph",
        "curated_rule",
        "mechanistic_baseline",
        "bayesian_graph",
        "orthogonal_consensus",
    }
)


class M1408DossierAuthorizationError(PermissionError):
    """Caller-owned controls do not authorize dossier publication."""

    def __init__(self) -> None:
        super().__init__(
            "M14-08 requires accepted controls, resolved identity, and granted consent"
        )


class M1408ReplayVerificationError(ValueError):
    """A dossier result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-08 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_dossier_authorization(candidate: object) -> None:
    """Check all seven controls before opaque evidence traversal."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001
        raise M1408DossierAuthorizationError from None
    if states != expected:
        raise M1408DossierAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_dossier_authorization(candidate)
    return candidate


def _evidence(
    request: PublishProteinSubtypeMechanismDossierRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_mechanism_result,
        *request.source_artifacts,
        request.configuration.model_reference,
        *(item.reference for item in request.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        *(item.source_artifact for item in request.dossier.links),
        *(item.reference for item in request.dossier.evidence),
    ]
    for link in request.dossier.links:
        artifacts.extend(item.reference for item in link.evidence)
        artifacts.extend(item.reference for item in link.counter_evidence)
    for claim in request.dossier.claims:
        artifacts.extend(item.reference for item in claim.evidence)
        artifacts.extend(item.reference for item in claim.counter_evidence)
    for route in request.dossier.validation_routes:
        artifacts.extend(item.reference for item in route.evidence)
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1408_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _counter_evidence(
    request: PublishProteinSubtypeMechanismDossierRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="counter_evidence",
            claim=(
                "Caller-declared dossier counter-evidence; issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts[:64]
    )


def _failure(
    request: PublishProteinSubtypeMechanismDossierRequest,
    *,
    code: DossierFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[DossierFinding, ...]:
    return (
        DossierFinding(
            finding_id=f"finding.{request.request_id}",
            code=code,
            message=message,
            evidence=evidence,
        ),
    )


def _evaluate_dossier(
    request: PublishProteinSubtypeMechanismDossierRequest,
) -> tuple[bool, DossierFindingCode | None, str | None]:
    dossier: MechanismEvidenceDossier = request.dossier
    if request.configuration.method not in _SUPPORTED_METHODS:
        return (
            False,
            DossierFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
            ("Dossier method is outside the closed review support domain."),
        )
    if any(
        route.status is not ValidationRouteStatus.COMPLETE for route in dossier.validation_routes
    ):
        return (
            False,
            DossierFindingCode.VALIDATION_ROUTE_REQUIRED,
            ("Every declared validation route must be complete before review-ready release."),
        )
    if any(
        link.disposition in {EvidenceDisposition.UNRESOLVED, EvidenceDisposition.ABSTAINED}
        for link in dossier.links
    ):
        return (
            False,
            DossierFindingCode.BROKEN_EVIDENCE_CHAIN,
            ("Unresolved or abstained evidence links block review-ready publication."),
        )
    if any(not claim.counter_evidence or not claim.evidence for claim in dossier.claims):
        return (
            False,
            DossierFindingCode.COUNTER_EVIDENCE_REQUIRED,
            ("Every mechanism claim requires evidence and counter-evidence."),
        )
    return True, None, None


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_inputs",
            statement="Artifact references are immutable and are never traversed by this runtime.",
        ),
        Limitation(
            code="reconstructable_chain",
            statement=(
                "Links, claims, validation routes, counter-evidence, and claim ceiling "
                "remain attached."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, generic all-omics fusion, treatment recommendation, "
                "identity inference, or consent inference is emitted."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "No review-ready dossier is published outside the closed evidence "
                    "support domain."
                ),
            )
        )
    return tuple(values)


class M1408DossierEngine:
    """Publish a caller-declared reconstructable dossier with replay."""

    __slots__ = ()

    def infer(self, request: object) -> ProteinSubtypeMechanismEvidenceDossierResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: PublishProteinSubtypeMechanismDossierRequest
    ) -> ProteinSubtypeMechanismEvidenceDossierResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        supported, failure_code, failure_message = _evaluate_dossier(request)
        findings = (
            ()
            if supported
            else _failure(
                request,
                code=failure_code or DossierFindingCode.BROKEN_EVIDENCE_CHAIN,
                message=failure_message or "Mechanism dossier was not safely evaluable.",
                evidence=evidence,
            )
        )
        payload: dict[str, object] = {
            "output_type": "protein_subtype_mechanism_evidence_dossier",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1408_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": DossierStatus.REVIEW_READY if supported else DossierStatus.ABSTAINED,
            "dossier": request.dossier if supported else None,
            "findings": findings,
            "abstention_reason": None
            if supported
            else (failure_message or "Mechanism dossier was not safely evaluable."),
            "parent_target": M1408_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m1408_dossier_review_ready"
                if supported
                else "m1408_dossier_abstained",
                rationale=(
                    (
                        "Evidence links, claims, validation routes, counter-evidence, and "
                        "claim ceiling are complete."
                    )
                    if supported
                    else "The dossier is outside the safely reviewable support domain."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=False),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": True,
        }
        constructed = ProteinSubtypeMechanismEvidenceDossierResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeMechanismEvidenceDossierResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1408ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1408ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1408ReplayVerificationError
        return validated


def publish_protein_subtype_mechanism_dossier(
    request: object,
) -> ProteinSubtypeMechanismEvidenceDossierResult:
    """Public provisional M14-08 operation."""

    return M1408DossierEngine().infer(request)


__all__ = [
    "M1408DossierAuthorizationError",
    "M1408DossierEngine",
    "M1408ReplayVerificationError",
    "preflight_dossier_authorization",
    "publish_protein_subtype_mechanism_dossier",
    "result_payload_digest",
]
