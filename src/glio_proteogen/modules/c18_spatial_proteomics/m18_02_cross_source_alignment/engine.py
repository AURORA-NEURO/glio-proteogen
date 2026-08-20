"""Deterministic authorization-first M18-02 alignment engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_02 import (
    M1802_CONTRACT_VERSION,
    M1802_EVIDENCE_CLAIM,
    M1802_MODULE_ID,
    AlignBiomarkerPanelSourcesRequest,
    AlignedEvidenceBundle,
    AlignmentFinding,
    AlignmentFindingCode,
    AlignmentObservationStatus,
    AlignmentStatus,
    BiomarkerPanelAlignmentResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
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

_REQUEST_ADAPTER: Final = TypeAdapter(AlignBiomarkerPanelSourcesRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelAlignmentResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1802AuthorizationError(PermissionError):
    """Caller controls do not authorize alignment."""

    def __init__(self) -> None:
        super().__init__(
            "M18-02 requires accepted controls, resolved identity, and granted consent"
        )


class M1802ReplayVerificationError(ValueError):
    """An M18-02 result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M18-02 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1802_authorization(candidate: object) -> None:
    """Check seven caller-declared controls before traversing source material."""

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
        raise M1802AuthorizationError from None
    if states != expected:
        raise M1802AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1802_authorization(candidate)
    return candidate


def _evidence(request: AlignBiomarkerPanelSourcesRequest) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
        *(evidence.reference for item in request.observations for evidence in item.evidence),
        *(evidence.reference for item in request.discrepancies for evidence in item.evidence),
        *(evidence.reference for evidence in request.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1802_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, estimable: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if estimable else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if estimable else None,
        rationale=(
            "Caller-declared source dimensions, support and controls are evaluable."
            if estimable
            else "A conflict, incomplete input, or unsupported source prevents safe alignment."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Alignment is deterministic over caller-declared source values and references.",
            "Missing or unsupported evidence is never converted into a negative finding.",
        ),
    )


def _provenance(
    request: AlignBiomarkerPanelSourcesRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in controls
    )
    input_digests = tuple(
        dict.fromkeys(
            (
                request_digest,
                request.upstream_result.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(
                    evidence.reference.digest
                    for item in request.observations
                    for evidence in item.evidence
                ),
                *(
                    evidence.reference.digest
                    for item in request.discrepancies
                    for evidence in item.evidence
                ),
                *(evidence.reference.digest for evidence in request.configuration.evidence),
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1802_MODULE_ID,
        module_version=M1802_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _classify(
    request: AlignBiomarkerPanelSourcesRequest,
) -> tuple[AlignmentStatus, tuple[AlignmentFindingCode, ...]]:
    findings: list[AlignmentFindingCode] = []
    if request.support_decision.status is not SupportStatus.SUPPORTED:
        findings.append(AlignmentFindingCode.UPSTREAM_UNSUPPORTED)
    if any(item.status is AlignmentObservationStatus.CONFLICTED for item in request.observations):
        findings.append(AlignmentFindingCode.DIMENSION_CONFLICT)
    if any(
        item.status is AlignmentObservationStatus.NOT_EVALUABLE for item in request.observations
    ):
        findings.append(AlignmentFindingCode.INPUT_INCOMPLETE)
    if any(item.resolution is None for item in request.discrepancies):
        findings.append(AlignmentFindingCode.DISCREPANCY_UNRESOLVED)
    if findings:
        return AlignmentStatus.ABSTAINED, tuple(dict.fromkeys(findings))
    findings.append(AlignmentFindingCode.PROVISIONAL_ABI_PENDING_REVIEW)
    return AlignmentStatus.ALIGNED, tuple(findings)


def _findings(
    codes: tuple[AlignmentFindingCode, ...],
    evidence: tuple[EvidenceReference, ...],
) -> tuple[AlignmentFinding, ...]:
    messages = {
        AlignmentFindingCode.DIMENSION_CONFLICT: (
            "One or more alignment dimensions conflict across sources."
        ),
        AlignmentFindingCode.INPUT_INCOMPLETE: "An alignment dimension is not safely evaluable.",
        AlignmentFindingCode.IDENTITY_MISMATCH: "Source identity does not safely align.",
        AlignmentFindingCode.REFERENCE_MISMATCH: (
            "Reference context is not compatible across sources."
        ),
        AlignmentFindingCode.DISCREPANCY_UNRESOLVED: (
            "A discrepancy remains unresolved and requires review."
        ),
        AlignmentFindingCode.UPSTREAM_UNSUPPORTED: (
            "Upstream support is outside the alignment envelope."
        ),
        AlignmentFindingCode.PROVISIONAL_ABI_PENDING_REVIEW: (
            "The provisional ABI requires governed owner review."
        ),
    }
    return tuple(
        AlignmentFinding(
            finding_id=f"finding.m1802.{code.value}",
            code=code,
            message=messages[code],
            evidence=evidence[:1],
        )
        for code in codes
    )


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_alignment",
            statement=(
                "Source identity, dimensions, references, support, and controls are "
                "caller-declared."
            ),
        ),
        Limitation(
            code="aligned_bundle_only",
            statement=(
                "The service emits only an aligned evidence bundle and discrepancy map; "
                "it never emits the biomarker-panel parent result."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No generic all-omics fusion, kinase activity, treatment recommendation, "
                "identity inference, or consent inference is emitted."
            ),
        ),
    ]
    if abstained:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "Conflicts, incomplete inputs, or unsupported sources produce no aligned "
                    "bundle."
                ),
            )
        )
    return tuple(values)


class M1802CrossSourceAlignmentEngine:
    """Align seven source dimensions while preserving conflicts and provenance."""

    __slots__ = ()

    def infer(self, request: object) -> BiomarkerPanelAlignmentResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: AlignBiomarkerPanelSourcesRequest,
    ) -> BiomarkerPanelAlignmentResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        status, codes = _classify(request)
        bundle = None
        if status is AlignmentStatus.ALIGNED:
            bundle = AlignedEvidenceBundle(
                bundle_id=f"bundle.{request_hash.removeprefix('sha256:')}",
                version=M1802_CONTRACT_VERSION,
                source_artifacts=request.source_artifacts,
                observations=request.observations,
                discrepancies=request.discrepancies,
                configuration=request.configuration,
                evidence=evidence,
            )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1802_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "aligned_bundle": bundle,
            "findings": _findings(codes, evidence),
            "abstention_reason": None if bundle is not None else "Sources are not safely aligned.",
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": (
                request.support_decision
                if bundle is not None
                else SupportDecision(
                    status=SupportStatus.REVIEW_REQUIRED,
                    reason_code="m1802_alignment_abstained",
                    rationale=(
                        "Conflict, incompleteness, or support limitations prevent safe alignment."
                    ),
                )
            ),
            "uncertainty": _uncertainty(estimable=bundle is not None),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(abstained=bundle is None),
            "human_review_required": bundle is None or bool(request.discrepancies),
        }
        constructed = BiomarkerPanelAlignmentResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelAlignmentResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1802ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1802ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1802ReplayVerificationError
        return validated


def align_biomarker_panel_sources(
    request: object,
) -> BiomarkerPanelAlignmentResult:
    """Public provisional M18-02 operation."""

    return M1802CrossSourceAlignmentEngine().infer(request)


__all__ = [
    "M1802AuthorizationError",
    "M1802CrossSourceAlignmentEngine",
    "M1802ReplayVerificationError",
    "align_biomarker_panel_sources",
    "preflight_m1802_authorization",
]
