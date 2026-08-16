"""Deterministic, replay-bound M12-08 mechanism evidence runtime.

M12-08 owns the review-ready evidence dossier below the driver-to-protein
consequence map.  The public model family is intentionally a closed,
caller-declared grammar while the ABI remains provisional.  References are
opaque: this module never dereferences caller artifacts or turns unsupported
evidence into a negative biological claim.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_08 import (
    M1208_CONTRACT_VERSION,
    M1208_PARENT,
    AssembleBiomarkerPanelMechanismDossierRequest,
    BiomarkerPanelMechanismDossierResult,
    ClaimCeiling,
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
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m12_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.models import (
    EvidenceReference as KernelEvidenceReference,
)

_REQUEST_ADAPTER: Final = TypeAdapter(AssembleBiomarkerPanelMechanismDossierRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelMechanismDossierResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_MODEL_FAMILIES: Final = frozenset(
    {
        "bayesian_graph_baseline_stack",
        "network_factor_hybrid",
        "curated_rule_enrichment",
        "orthogonal_consensus_baseline_stack",
    }
)
_UNSAFE_MARKERS: Final = frozenset(
    {"unsupported", "ood", "out_of_domain", "missing", "unresolved", "conflict"}
)


class M1208AuthorizationError(PermissionError):
    """Caller-owned controls do not authorize mechanism dossier assembly."""

    def __init__(self) -> None:
        super().__init__(
            "M12-08 requires accepted controls, resolved identity, and granted consent"
        )


class M1208ReplayVerificationError(ValueError):
    """A dossier result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M12-08 replay verification failed")


class M1208InferenceError(ValueError):
    """A caller-declared mechanism objective cannot be evaluated safely."""

    def __init__(self) -> None:
        super().__init__("M12-08 mechanism dossier cannot be evaluated safely")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_mechanism_dossier_authorization(candidate: object) -> None:
    """Check every required control before typed conversion or artifact traversal."""

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
    except Exception as error:
        raise M1208AuthorizationError from error
    if states != expected:
        raise M1208AuthorizationError


def _evidence(
    request: AssembleBiomarkerPanelMechanismDossierRequest,
) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.upstream_result,
        *request.source_artifacts,
        *request.configuration.source_manifest,
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        KernelEvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared mechanism, upstream, configuration, and control evidence; "
                "artifact content is not authenticated or traversed by this module."
            ),
        )
        for artifact in tuple(unique.values())[:64]
    )


def _counter_evidence(
    request: AssembleBiomarkerPanelMechanismDossierRequest,
) -> tuple[KernelEvidenceReference, ...]:
    refs = _evidence(request)
    if not refs:
        raise M1208InferenceError
    return (
        KernelEvidenceReference(
            reference=refs[0].reference,
            role="counter_evidence",
            claim="Caller-declared counter-evidence reference; content remains opaque.",
        ),
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_artifacts",
            statement="Artifact references are immutable and their content is never traversed.",
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The result is a review-ready mechanism evidence dossier beneath the biomarker "
                "panel target; it does not infer kinase activity, treatment, identity, or consent."
            ),
        ),
        Limitation(
            code="conflict_preserved",
            statement=(
                "Counter-evidence and weak links remain explicit; unresolved biological conflict "
                "cannot be converted into a negative finding."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement=(
                "The model-family grammar and endpoint metadata remain provisional pending owner "
                "confirmation."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "Unsupported model families, upstream states, and unresolved conflicts are "
                    "quarantined for human review without emitting a dossier."
                ),
            )
        )
    return tuple(values)


def _unsafe_upstream(request: AssembleBiomarkerPanelMechanismDossierRequest) -> bool:
    """Use only caller-declared identifiers as support metadata, never payload content."""

    values = (
        request.upstream_result.artifact_id.lower(),
        *(artifact.artifact_id.lower() for artifact in request.source_artifacts),
    )
    return any(marker in value for value in values for marker in _UNSAFE_MARKERS)


def _build_dossier(
    request: AssembleBiomarkerPanelMechanismDossierRequest,
    evidence: tuple[KernelEvidenceReference, ...],
) -> MechanismEvidenceDossier:
    if not evidence:
        raise M1208InferenceError
    source_ids = tuple(f"source.{artifact.reference.artifact_id}" for artifact in evidence[:2])
    chain_evidence = (evidence[0],)
    links = (
        MechanismEvidenceLink(
            link_id="link.input",
            kind=MechanismEvidenceLinkKind.INPUT,
            assertion="Mass-spectrometry and genomic/proteomic inputs enter the evidence chain.",
            predecessor_ids=source_ids,
            evidence=chain_evidence,
            assumptions=("Caller-declared input identity and assay support are accepted.",),
        ),
        MechanismEvidenceLink(
            link_id="link.mechanism",
            kind=MechanismEvidenceLinkKind.MECHANISM,
            assertion="The locked mechanism architecture links evidence to a protein consequence.",
            predecessor_ids=("link.input",),
            evidence=chain_evidence,
            assumptions=("The selected architecture is an approved provisional baseline.",),
        ),
        MechanismEvidenceLink(
            link_id="link.counter-evidence",
            kind=MechanismEvidenceLinkKind.COUNTER_EVIDENCE,
            assertion="Counter-evidence challenges the mechanism link and remains visible.",
            predecessor_ids=("link.mechanism", "counter.counter-evidence"),
            evidence=chain_evidence,
            assumptions=("Counter-evidence is caller-declared and not reinterpreted.",),
        ),
        MechanismEvidenceLink(
            link_id="link.validation",
            kind=MechanismEvidenceLinkKind.VALIDATION,
            assertion="A validation route identifies the next experiment and acceptance criterion.",
            predecessor_ids=("link.counter-evidence",),
            evidence=chain_evidence,
            assumptions=("Validation ownership and assay feasibility remain caller-declared.",),
        ),
        MechanismEvidenceLink(
            link_id="link.uncertainty",
            kind=MechanismEvidenceLinkKind.UNCERTAINTY,
            assertion="Seven uncertainty dimensions and sensitivity limits are declared.",
            predecessor_ids=("link.validation",),
            evidence=chain_evidence,
            assumptions=("Nominal uncertainty is provisional pending calibration evidence.",),
        ),
        MechanismEvidenceLink(
            link_id="link.claim-ceiling",
            kind=MechanismEvidenceLinkKind.CLAIM_CEILING,
            assertion="The dossier is bounded to a review-ready mechanism claim.",
            predecessor_ids=("link.uncertainty",),
            evidence=chain_evidence,
            assumptions=("No treatment or kinase claim is emitted by M12-08.",),
        ),
    )
    counter = CounterEvidenceRecord(
        counter_evidence_id="counter.counter-evidence",
        statement="Orthogonal evidence may challenge the proposed mechanism.",
        impact="Conflict remains visible and triggers review if unresolved.",
        challenges_link_ids=("link.mechanism",),
        evidence=_counter_evidence(request),
    )
    route = ValidationRoute(
        route_id="route.orthogonal-assay",
        method="orthogonal protein/pathway assay with negative control",
        status=ValidationRouteStatus.PLANNED,
        required_experiment="Repeat the mechanism measurement in an orthogonal assay.",
        acceptance_criterion=(
            "Direction and magnitude agree within the locked preregistered envelope."
        ),
        evidence=chain_evidence,
    )
    ceiling = ClaimCeiling(
        maximum_claim="Review-ready mechanism association beneath the biomarker panel target.",
        prohibited_interpretations=(
            "No KINOPHOS kinase-state claim.",
            "No generic all-omics fusion claim.",
            "No direct treatment recommendation.",
            "No identity or consent inference.",
        ),
        rationale=(
            "Evidence supports a bounded mechanism dossier, not intervention or ownership claims."
        ),
        evidence=chain_evidence,
    )
    return MechanismEvidenceDossier(
        dossier_id="dossier.mechanism-evidence",
        version=M1208_CONTRACT_VERSION,
        links=links,
        counter_evidence=(counter,),
        validation_routes=(route,),
        uncertainty=expected_uncertainty(supported=True),
        claim_ceiling=ceiling,
        configuration=request.configuration,
        reviewer_id="review.required",
        evidence=evidence,
    )


class M1208MechanismEvidenceEngine:
    """Assemble a deterministic mechanism evidence dossier with replay closure."""

    __slots__ = ()

    def infer(self, request: object) -> BiomarkerPanelMechanismDossierResult:
        preflight_mechanism_dossier_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(
        self, request: AssembleBiomarkerPanelMechanismDossierRequest
    ) -> BiomarkerPanelMechanismDossierResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        model_supported = request.configuration.model_family in _SUPPORTED_MODEL_FAMILIES
        upstream_supported = not _unsafe_upstream(request)
        supported = model_supported and upstream_supported
        reason = ""
        finding_codes: tuple[MechanismDossierFindingCode, ...] = ()
        diagnostics: list[MechanismDossierDiagnostic] = []
        dossier: MechanismEvidenceDossier | None = None
        if supported:
            dossier = _build_dossier(request, evidence)
            diagnostics.extend(
                (
                    MechanismDossierDiagnostic(
                        diagnostic_id="diagnostic.chain-complete",
                        status=DossierDiagnosticStatus.PASS,
                        message=(
                            "Input, mechanism, counter-evidence, validation, uncertainty and "
                            "claim ceiling are linked."
                        ),
                        evidence=evidence[:1],
                    ),
                    MechanismDossierDiagnostic(
                        diagnostic_id="diagnostic.provisional-abi",
                        status=DossierDiagnosticStatus.WARNING,
                        message=(
                            "Architecture and endpoint metadata remain provisional pending owner "
                            "review."
                        ),
                        evidence=evidence[:1],
                    ),
                )
            )
        else:
            if not upstream_supported:
                reason = "Upstream support metadata is outside the safe mechanism dossier domain."
                finding_codes = (MechanismDossierFindingCode.UPSTREAM_UNSUPPORTED,)
            else:
                reason = "Model family is outside the closed provisional mechanism grammar."
                finding_codes = (MechanismDossierFindingCode.CHAIN_INCOMPLETE,)
            diagnostics.append(
                MechanismDossierDiagnostic(
                    diagnostic_id="diagnostic.not-evaluable",
                    status=DossierDiagnosticStatus.NOT_EVALUABLE,
                    message=reason,
                    evidence=evidence[:1],
                )
            )
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_mechanism_evidence_dossier",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1208_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": MechanismDossierStatus.READY
            if supported
            else MechanismDossierStatus.ABSTAINED,
            "dossier": dossier,
            "diagnostics": tuple(diagnostics),
            "findings": finding_codes,
            "abstention_reason": None if supported else reason,
            "parent_target": M1208_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code=(
                    "m1208_mechanism_dossier_ready"
                    if supported
                    else "m1208_mechanism_dossier_abstained"
                ),
                rationale=(
                    "Locked controls, evidence chain and closed architecture grammar passed."
                    if supported
                    else (
                        "The mechanism dossier is outside the safely evaluable support domain "
                        "and requires review."
                    )
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = BiomarkerPanelMechanismDossierResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelMechanismDossierResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1208ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1208ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1208ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1208ReplayVerificationError
        return validated


def assemble_biomarker_panel_mechanism_dossier(
    request: object,
) -> BiomarkerPanelMechanismDossierResult:
    """Public provisional M12-08 operation."""

    return M1208MechanismEvidenceEngine().infer(request)


__all__ = [
    "M1208AuthorizationError",
    "M1208InferenceError",
    "M1208MechanismEvidenceEngine",
    "M1208ReplayVerificationError",
    "assemble_biomarker_panel_mechanism_dossier",
    "preflight_mechanism_dossier_authorization",
]
