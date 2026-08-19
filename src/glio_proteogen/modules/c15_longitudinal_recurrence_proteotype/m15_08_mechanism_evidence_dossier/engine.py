"""Replay-safe M15-08 mechanism evidence dossier assembly.

The dossier leaves the scientific ABI open.  This runtime therefore assembles
only a caller-declared, reconstructable evidence graph.  It never reads source
bytes, fits a mechanism, performs all-omics fusion, emits kinase activity,
relabels upstream results, recommends treatment, or turns missing/support-
limited evidence into a negative finding.  Validation remains planned and
weak links stay visible until Clinical science owner review.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_08 import (
    M1508_CONTRACT_VERSION,
    M1508_MODULE_ID,
    M1508_PARENT,
    AssembleComplexActivityMechanismDossierRequest,
    ClaimCeiling,
    ComplexActivityMechanismDossierResult,
    CounterEvidenceRecord,
    DossierDiagnosticStatus,
    MechanismDossierDiagnostic,
    MechanismDossierFindingCode,
    MechanismDossierStatus,
    MechanismEvidenceDossier,
    MechanismEvidenceLink,
    MechanismEvidenceLinkKind,
    ValidationRoute,
    ValidationRouteStatus,
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

_REQUEST_ADAPTER: Final = TypeAdapter(AssembleComplexActivityMechanismDossierRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityMechanismDossierResult)
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
            "M15-08 preserves artifact declarations as immutable references and never reads "
            "their source bytes."
        ),
    ),
    Limitation(
        code="metadata_chain_replay",
        statement=(
            "The evidence chain is caller-declared metadata; no biological mechanism or "
            "proteogenomic state is inferred."
        ),
    ),
    Limitation(
        code="validation_planned",
        statement=(
            "Required validation experiments remain planned until an owner-approved route "
            "and evidence receipt are supplied."
        ),
    ),
    Limitation(
        code="provisional_abi",
        statement=(
            "The public dossier ABI remains provisional pending Clinical science owner "
            "confirmation of the authoritative slice."
        ),
    ),
)
_CLAIM_PROHIBITIONS: Final = (
    "KINOPHOS-owned kinase activity",
    "generic all-omics fusion",
    "direct treatment recommendation",
    "identity or consent inference",
    "relabeling upstream evidence or erasing disagreement",
    "unsupported or missing evidence converted into a negative finding",
)


class M1508AuthorizationError(PermissionError):
    """Caller controls do not authorize dossier assembly."""

    def __init__(self) -> None:
        super().__init__(
            "M15-08 requires accepted controls, resolved identity, and granted consent"
        )


class M1508ReplayVerificationError(ValueError):
    """A dossier result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M15-08 replay verification failed")


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-08 request must be a strict request model or mapping")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1508_authorization(candidate: object) -> None:
    """Check all seven controls before traversing the dossier inputs."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state")) for role in _EXPECTED_CONTROLS
        }
    except Exception as error:
        raise M1508AuthorizationError from error
    if states != _EXPECTED_CONTROLS:
        raise M1508AuthorizationError


def _as_request(candidate: object) -> AssembleComplexActivityMechanismDossierRequest:
    preflight_m1508_authorization(candidate)
    if type(candidate) is AssembleComplexActivityMechanismDossierRequest:
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise _InvalidRequestError


def _evidence(
    request: AssembleComplexActivityMechanismDossierRequest,
) -> tuple[EvidenceReference, ...]:
    references: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
        *request.configuration.source_manifest,
    ]
    references.extend(item.reference for item in request.configuration.evidence)
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
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=(
                "Caller-declared M15-08 mechanism evidence; issuer authority and scientific "
                "truth are not authenticated."
            ),
        )
        for reference in unique
    )


def _controls(
    request: AssembleComplexActivityMechanismDossierRequest,
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
        "parameter": "No fitted mechanism parameters or parameter uncertainty are evaluated.",
        "model_form": "The dossier leaves the mechanism ABI and architecture open.",
        "identification": "Identity, lineage, and proteogenomic state are not inferred.",
        "support": "Support reflects caller controls, not external evidence authenticity.",
        "transport": (
            "Transport across cohorts, assays, territories, and treatment eras is not estimable."
        ),
    }
    estimates = {
        name: UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)
        for name, reason in values.items()
    }
    return UncertaintyProfile(
        **estimates,
        sensitivity_notes=(
            "Chain replay is deterministic but contains no quantitative mechanism estimate.",
            "Human review is required before claim promotion or release exception.",
        ),
    )


def _provenance(
    request: AssembleComplexActivityMechanismDossierRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m1508.{request_hash.removeprefix('sha256:')[:32]}",
        actor_id=request.context.actor_id,
        module_id=M1508_MODULE_ID,
        module_version=M1508_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
            *(artifact.digest for artifact in request.configuration.source_manifest),
        ),
        configuration_digest=sha256_digest(request.configuration.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _dossier(
    request: AssembleComplexActivityMechanismDossierRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> MechanismEvidenceDossier:
    chain_evidence = evidence[:1]
    links = (
        MechanismEvidenceLink(
            link_id="link.m1508.input",
            kind=MechanismEvidenceLinkKind.INPUT,
            assertion=(
                "Declared proteome, genome/transcriptome, PTM, and upstream context enter "
                "the mechanism evidence chain."
            ),
            predecessor_ids=("counter-evidence.m1508.primary",),
            evidence=chain_evidence,
            assumptions=("Input declarations are caller-owned and remain opaque.",),
        ),
        MechanismEvidenceLink(
            link_id="link.m1508.mechanism",
            kind=MechanismEvidenceLinkKind.MECHANISM,
            assertion=(
                "A mechanism association is retained as a caller-declared assertion for "
                "review; no mechanism is inferred by this runtime."
            ),
            predecessor_ids=("link.m1508.input",),
            evidence=chain_evidence,
            assumptions=("Mechanism semantics require owner and reviewer confirmation.",),
        ),
        MechanismEvidenceLink(
            link_id="link.m1508.validation",
            kind=MechanismEvidenceLinkKind.VALIDATION,
            assertion="Validation route and acceptance criterion are explicitly declared.",
            predecessor_ids=("link.m1508.mechanism",),
            evidence=chain_evidence,
            assumptions=("Required experiment is not represented as completed evidence.",),
        ),
        MechanismEvidenceLink(
            link_id="link.m1508.uncertainty",
            kind=MechanismEvidenceLinkKind.UNCERTAINTY,
            assertion=(
                "Measurement, sampling, parameter, model-form, identification, support, "
                "and transport uncertainty remain visible."
            ),
            predecessor_ids=("link.m1508.validation",),
            evidence=chain_evidence,
            assumptions=("Uncertainty values are not estimable from opaque declarations.",),
        ),
        MechanismEvidenceLink(
            link_id="link.m1508.claim-ceiling",
            kind=MechanismEvidenceLinkKind.CLAIM_CEILING,
            assertion="Claim ceiling and prohibited interpretations are preserved for review.",
            predecessor_ids=("link.m1508.uncertainty",),
            evidence=chain_evidence,
            assumptions=("No unsupported claim may be promoted by this module.",),
        ),
    )
    counter_evidence = (
        CounterEvidenceRecord(
            counter_evidence_id="counter-evidence.m1508.primary",
            statement=(
                "The caller-declared mechanism association has no authenticated orthogonal "
                "counter-evidence at this metadata-only boundary."
            ),
            impact="Weakens promotion and requires owner/reviewer resolution before release.",
            challenges_link_ids=("link.m1508.mechanism",),
            evidence=chain_evidence,
        ),
    )
    validation_routes = (
        ValidationRoute(
            route_id="validation-route.m1508.orthogonal",
            method=(
                "orthogonal assay, negative-control gating, and independent reviewer reconstruction"
            ),
            status=ValidationRouteStatus.PLANNED,
            required_experiment=(
                "Supply an owner-approved orthogonal experiment that tests the declared "
                "mechanism and relevant negative control."
            ),
            acceptance_criterion=(
                "Reviewer reconstructs every link, identifies weak links, and records the "
                "preregistered support decision without erasing disagreement."
            ),
            evidence=chain_evidence,
        ),
    )
    claim_ceiling = ClaimCeiling(
        maximum_claim=(
            "Review-ready, caller-declared mechanism evidence dossier supporting follow-up "
            "experiments; not a biological or treatment conclusion."
        ),
        prohibited_interpretations=_CLAIM_PROHIBITIONS,
        rationale=(
            "The dossier slice requires explicit uncertainty, counter-evidence, validation, "
            "and claim ceiling; this ABI cannot authenticate or interpret source content."
        ),
        evidence=chain_evidence,
    )
    return MechanismEvidenceDossier(
        dossier_id=f"dossier.m1508.{request_hash.removeprefix('sha256:')[:32]}",
        version=M1508_CONTRACT_VERSION,
        links=links,
        counter_evidence=counter_evidence,
        validation_routes=validation_routes,
        uncertainty=_uncertainty(),
        claim_ceiling=claim_ceiling,
        configuration=request.configuration,
        reviewer_id=request.context.actor_id,
        evidence=evidence,
    )


class M1508MechanismDossierEngine:
    """Assemble a deterministic caller-declared mechanism evidence dossier."""

    __slots__ = ()

    def construct(self, request: object) -> ComplexActivityMechanismDossierResult:
        validated = _as_request(request)
        request_hash = canonical_request_digest(validated)
        evidence = _evidence(validated)
        dossier = _dossier(validated, evidence, request_hash)
        diagnostics = (
            MechanismDossierDiagnostic(
                diagnostic_id=f"diagnostic.m1508.{request_hash.removeprefix('sha256:')[:12]}.chain",
                status=DossierDiagnosticStatus.PASS,
                message="Every dossier link has an explicit predecessor and evidence reference.",
                evidence=evidence[:1],
            ),
            MechanismDossierDiagnostic(
                diagnostic_id=f"diagnostic.m1508.{request_hash.removeprefix('sha256:')[:12]}.counter",
                status=DossierDiagnosticStatus.PASS,
                message="Counter-evidence is visible and linked to the mechanism assertion.",
                evidence=evidence[:1],
            ),
            MechanismDossierDiagnostic(
                diagnostic_id=(
                    f"diagnostic.m1508.{request_hash.removeprefix('sha256:')[:12]}.validation"
                ),
                status=DossierDiagnosticStatus.WARNING,
                message=(
                    "Validation route is planned and requires owner-approved experiment evidence."
                ),
                evidence=evidence[:1],
            ),
            MechanismDossierDiagnostic(
                diagnostic_id=f"diagnostic.m1508.{request_hash.removeprefix('sha256:')[:12]}.abi",
                status=DossierDiagnosticStatus.WARNING,
                message="The scientific ABI is provisional pending Clinical science owner review.",
                evidence=evidence[:1],
            ),
        )
        payload: dict[str, object] = {
            "output_type": "complex_activity_mechanism_evidence_dossier",
            "result_id": f"result.m1508.{request_hash.removeprefix('sha256:')[:32]}",
            "result_version": M1508_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": "sha256:" + "0" * 64,
            "request": validated,
            "status": MechanismDossierStatus.READY,
            "dossier": dossier,
            "diagnostics": diagnostics,
            "findings": (MechanismDossierFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,),
            "abstention_reason": None,
            "parent_target": M1508_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1508_metadata_dossier_replay_supported",
                rationale=(
                    "A caller-declared reconstructable chain was assembled without reading "
                    "or interpreting opaque evidence."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(validated, request_hash),
            "evidence": evidence,
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        constructed = ComplexActivityMechanismDossierResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityMechanismDossierResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1508ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1508ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1508ReplayVerificationError
        expected = self.construct(validated.request).model_dump(mode="json")
        if replay and expected != validated.model_dump(mode="json"):
            raise M1508ReplayVerificationError
        return validated


def assemble_complex_activity_mechanism_dossier(
    request: object,
) -> ComplexActivityMechanismDossierResult:
    """Public provisional M15-08 operation."""

    return M1508MechanismDossierEngine().construct(request)


__all__ = [
    "M1508AuthorizationError",
    "M1508MechanismDossierEngine",
    "M1508ReplayVerificationError",
    "assemble_complex_activity_mechanism_dossier",
    "preflight_m1508_authorization",
]
