"""Replay-safe, component-specific M16-03 evidence aggregation.

The scientific ABI remains provisional. This runtime copies caller-declared
source contributions, reliability, signed propagation, and disagreement into
one attributable integrated object. It never reads opaque artifact bytes,
performs generic all-omics fusion, verifies signatures it cannot authenticate,
emits kinase state, recommends treatment, infers identity/consent, or converts
unsupported evidence into a negative finding. Low or un-evaluable reliability
fails closed with explicit abstention.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_03 import (
    M1603_CONTRACT_VERSION,
    M1603_EVIDENCE_CLAIM,
    M1603_MODULE_ID,
    M1603_PARENT,
    FuseProteinRnaDiscordanceEvidenceRequest,
    FusionFinding,
    FusionFindingCode,
    FusionStatus,
    IntegratedEvidenceObject,
    ProteinRnaDiscordanceIntegratedEvidenceResult,
    ReliabilityBand,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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

_REQUEST_ADAPTER: Final = TypeAdapter(FuseProteinRnaDiscordanceEvidenceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceIntegratedEvidenceResult)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_LIMITATIONS: Final = (
    Limitation(
        code="opaque_references",
        statement=(
            "M16-03 preserves artifacts as immutable references and never reads source bytes."
        ),
    ),
    Limitation(
        code="component_specific_only",
        statement=(
            "Contributions remain attributable; this is not generic all-omics fusion or "
            "a kinase-state computation."
        ),
    ),
    Limitation(
        code="signature_authority_external",
        statement="Signed propagation digests are caller-declared and require external authority.",
    ),
    Limitation(
        code="provisional_abi",
        statement="The public fusion ABI remains provisional pending Computational biology review.",
    ),
)


class M1603AuthorizationError(PermissionError):
    """Caller controls do not authorize component-specific aggregation."""

    def __init__(self) -> None:
        super().__init__(
            "M16-03 requires accepted controls, resolved identity, and granted consent"
        )


class M1603ReplayVerificationError(ValueError):
    """An aggregated result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M16-03 replay verification failed")


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M16-03 request must be a strict request model or mapping")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1603_authorization(candidate: object) -> None:
    """Check all seven controls before contribution or propagation traversal."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state")) for role in _EXPECTED_CONTROLS
        }
    except Exception as error:
        raise M1603AuthorizationError from error
    if states != _EXPECTED_CONTROLS:
        raise M1603AuthorizationError


def _as_request(candidate: object) -> FuseProteinRnaDiscordanceEvidenceRequest:
    preflight_m1603_authorization(candidate)
    if type(candidate) is FuseProteinRnaDiscordanceEvidenceRequest:
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise _InvalidRequestError


def _evidence(
    request: FuseProteinRnaDiscordanceEvidenceRequest,
) -> tuple[EvidenceReference, ...]:
    references: list[ArtifactReference] = [
        request.alignment_result,
        *request.source_artifacts,
        request.configuration.evidence[0].reference
        if request.configuration.evidence
        else request.source_artifacts[0],
    ]
    references.extend(item.artifact for item in request.contributions)
    references.extend(
        evidence.reference for item in request.contributions for evidence in item.evidence
    )
    references.extend(
        evidence.reference for item in request.disagreements for evidence in item.evidence
    )
    references.extend(
        evidence.reference for item in request.propagation for evidence in item.evidence
    )
    controls = request.context.references
    references.extend(
        (
            controls.approved_configuration.evidence,
            controls.identity_lineage.evidence,
            controls.provenance.evidence,
            controls.consent.evidence,
            controls.quality.evidence,
            controls.support.evidence,
            controls.intended_use.evidence,
        )
    )
    unique: list[ArtifactReference] = []
    seen: set[tuple[str, str, str, str]] = set()
    for reference in references:
        key = (reference.artifact_id, reference.version, reference.digest, reference.media_type)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=M1603_EVIDENCE_CLAIM)
        for reference in unique
    )


def _controls(
    request: FuseProteinRnaDiscordanceEvidenceRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in values
    )


def _uncertainty() -> UncertaintyProfile:
    values = {
        "measurement": "Measurement values are not read from opaque artifact references.",
        "sampling": "Sampling coverage and assay completeness are not evaluated here.",
        "parameter": "No fitted fusion parameters or parameter uncertainty are evaluated.",
        "model_form": "The dossier leaves the fusion architecture and propagation ABI open.",
        "identification": "Identity, lineage, and biological state are not inferred.",
        "support": "Support reflects caller controls, not external evidence authenticity.",
        "transport": "Transport across cohorts, assays, and treatment eras is not estimable.",
    }
    estimates = {
        name: UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)
        for name, reason in values.items()
    }
    return UncertaintyProfile(
        **estimates,
        sensitivity_notes=(
            (
                "Source attribution and disagreement preservation are replay-stable; no "
                "quantitative fusion is performed."
            ),
            "Owner review is required before propagation or integrated evidence claim promotion.",
        ),
    )


def _provenance(
    request: FuseProteinRnaDiscordanceEvidenceRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m1603.{request_hash.removeprefix('sha256:')[:32]}",
        actor_id=request.context.actor_id,
        module_id=M1603_MODULE_ID,
        module_version=M1603_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.alignment_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
            *(item.artifact.digest for item in request.contributions),
        ),
        configuration_digest=sha256_digest(request.configuration.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _finding(
    request_hash: str,
    code: FusionFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> FusionFinding:
    return FusionFinding(
        finding_id=f"finding.m1603.{request_hash.removeprefix('sha256:')[:12]}.{code}",
        code=code,
        message=message,
        evidence=evidence[:1],
    )


class M1603FusionEngine:
    """Aggregate attributable metadata while preserving disagreement and ownership."""

    __slots__ = ()

    def construct(self, request: object) -> ProteinRnaDiscordanceIntegratedEvidenceResult:
        validated = _as_request(request)
        request_hash = canonical_request_digest(validated)
        evidence = _evidence(validated)
        low_sources = tuple(
            item
            for item in validated.contributions
            if item.reliability_score < validated.configuration.reliability_threshold
        )
        unsafe_sources = tuple(
            item
            for item in validated.contributions
            if item.reliability_band is ReliabilityBand.NOT_EVALUABLE
        )
        findings = [
            _finding(
                request_hash,
                FusionFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "The fusion ABI and propagation semantics remain provisional pending owner review.",
                evidence,
            )
        ]
        if validated.disagreements:
            findings.append(
                _finding(
                    request_hash,
                    FusionFindingCode.SOURCE_DISAGREEMENT,
                    (
                        "Caller-declared source disagreements remain visible and block silent "
                        "resolution."
                    ),
                    evidence,
                )
            )
        if low_sources:
            findings.append(
                _finding(
                    request_hash,
                    FusionFindingCode.LOW_RELIABILITY,
                    (
                        "One or more source contributions are below the configured reliability "
                        "threshold."
                    ),
                    evidence,
                )
            )
        if unsafe_sources:
            findings.append(
                _finding(
                    request_hash,
                    FusionFindingCode.UNSUPPORTED_INPUT,
                    "One or more source contributions are not evaluable; aggregation abstains.",
                    evidence,
                )
            )
        abstain = bool(low_sources or unsafe_sources)
        integrated = None
        status = FusionStatus.ABSTAINED if abstain else FusionStatus.INTEGRATED
        if not abstain:
            integrated = IntegratedEvidenceObject(
                integrated_id=f"integrated.m1603.{request_hash.removeprefix('sha256:')[:32]}",
                version=M1603_CONTRACT_VERSION,
                contributions=validated.contributions,
                disagreements=validated.disagreements,
                propagation=validated.propagation,
                configuration=validated.configuration,
                evidence=evidence,
            )
        payload: dict[str, object] = {
            "output_type": "protein_rna_discordance_integrated_evidence",
            "result_id": f"result.m1603.{request_hash.removeprefix('sha256:')[:32]}",
            "result_version": M1603_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": "sha256:" + "0" * 64,
            "request": validated,
            "status": status,
            "integrated_evidence": integrated,
            "findings": tuple(findings),
            "abstention_reason": (
                "Reliability or support boundary prevents safe component-specific aggregation."
                if abstain
                else None
            ),
            "parent_target": M1603_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED if abstain else SupportStatus.SUPPORTED,
                reason_code=(
                    "m1603_reliability_boundary"
                    if abstain
                    else "m1603_attributable_integration_supported"
                ),
                rationale=(
                    "Aggregation abstained because reliability evidence is outside the "
                    "configured support envelope."
                    if abstain
                    else (
                        "Attributable source contributions were integrated without erasing "
                        "disagreement."
                    )
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(validated, request_hash),
            "evidence": evidence,
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        constructed = ProteinRnaDiscordanceIntegratedEvidenceResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceIntegratedEvidenceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1603ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1603ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1603ReplayVerificationError
        expected = self.construct(validated.request).model_dump(mode="json")
        if replay and expected != validated.model_dump(mode="json"):
            raise M1603ReplayVerificationError
        return validated


def fuse_protein_rna_discordance_evidence(
    request: object,
) -> ProteinRnaDiscordanceIntegratedEvidenceResult:
    """Public provisional M16-03 operation."""

    return M1603FusionEngine().construct(request)


__all__ = [
    "M1603AuthorizationError",
    "M1603FusionEngine",
    "M1603ReplayVerificationError",
    "fuse_protein_rna_discordance_evidence",
    "preflight_m1603_authorization",
]
