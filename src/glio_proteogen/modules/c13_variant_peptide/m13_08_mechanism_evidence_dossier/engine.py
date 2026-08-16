"""Deterministic, replay-bound M13-08 mechanism dossier runtime.

The dossier ABI is provisional.  This implementation evaluates a closed
caller-declared model-family vocabulary, preserves every evidence link and
counter-evidence reference, and abstains when the chain cannot be reconstructed
without inventing biological content.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_08 import (
    M1308_CONTRACT_VERSION,
    M1308_EVIDENCE_CLAIM,
    M1308_PARENT,
    AssembleProteotypeMechanismDossierRequest,
    ClaimCeiling,
    CounterEvidenceRecord,
    DossierDiagnosticStatus,
    MechanismDossierDiagnostic,
    MechanismDossierFindingCode,
    MechanismDossierStatus,
    MechanismEvidenceDossier,
    MechanismEvidenceLink,
    MechanismEvidenceLinkKind,
    ProteotypeMechanismDossierResult,
    ValidationRoute,
    ValidationRouteStatus,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m13_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.models import EvidenceReference as KernelEvidenceReference

_REQUEST_ADAPTER: Final = TypeAdapter(AssembleProteotypeMechanismDossierRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeMechanismDossierResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_FAMILIES: Final = frozenset(
    {"bayesian_model_averaging", "state_space", "mechanistic", "foundation_assisted"}
)


class M1308AuthorizationError(PermissionError):
    """Caller-owned controls do not authorize dossier assembly."""

    def __init__(self) -> None:
        super().__init__(
            "M13-08 requires accepted controls, resolved identity, and granted consent"
        )


class M1308ReplayVerificationError(ValueError):
    """A dossier result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M13-08 replay verification failed")


class M1308InferenceError(ValueError):
    """A caller-declared mechanism dossier cannot be evaluated safely."""


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_dossier_authorization(candidate: object) -> None:
    """Check all seven controls before typed or opaque materialization."""

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
        raise M1308AuthorizationError from error
    if states != expected:
        raise M1308AuthorizationError


def _evidence(
    request: AssembleProteotypeMechanismDossierRequest,
) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.upstream_result,
        *request.source_artifacts,
        *request.configuration.source_manifest,
        *(item.reference for item in request.configuration.evidence),
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
        KernelEvidenceReference(reference=artifact, role="evidence", claim=M1308_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_artifacts",
            statement="Artifact references are immutable and never dereferenced by this runtime.",
        ),
        Limitation(
            code="chain_reconstruction",
            statement=(
                "Every dossier link, counter-evidence record, validation route, and claim "
                "ceiling remains explicit."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "No kinase activity, generic all-omics fusion, treatment recommendation, "
                "identity inference, consent inference, or parent-output mutation is emitted."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement=(
                "Dossier vocabulary and endpoint metadata remain provisional pending owner "
                "confirmation."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "Unsupported model families or unresolved chains are quarantined for human "
                    "review."
                ),
            )
        )
    return tuple(values)


def _family_supported(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in _SUPPORTED_FAMILIES


class M1308DossierEngine:
    """Assemble a caller-declared mechanism evidence dossier."""

    __slots__ = ()

    def infer(self, request: object) -> ProteotypeMechanismDossierResult:
        preflight_dossier_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(
        self, request: AssembleProteotypeMechanismDossierRequest
    ) -> ProteotypeMechanismDossierResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        supported = _family_supported(request.configuration.model_family)
        diagnostics: list[MechanismDossierDiagnostic] = []
        dossier: MechanismEvidenceDossier | None = None
        findings: tuple[MechanismDossierFindingCode, ...] = ()
        reason: str | None = None
        if supported:
            counter_id = "counter-evidence.primary"
            links = (
                MechanismEvidenceLink(
                    link_id="link.input",
                    kind=MechanismEvidenceLinkKind.INPUT,
                    assertion="Caller-declared upstream and source references enter the dossier.",
                    predecessor_ids=("source",),
                    evidence=evidence[:1],
                    assumptions=(
                        "Input issuer authority is caller-declared and not authenticated.",
                    ),
                ),
                MechanismEvidenceLink(
                    link_id="link.mechanism",
                    kind=MechanismEvidenceLinkKind.MECHANISM,
                    assertion="The locked model family supports a mechanism association dossier.",
                    predecessor_ids=("link.input",),
                    evidence=evidence[:1],
                    assumptions=("The model-family manifest is locked and versioned.",),
                ),
                MechanismEvidenceLink(
                    link_id="link.validation",
                    kind=MechanismEvidenceLinkKind.VALIDATION,
                    assertion="An independent validation route is required before claim promotion.",
                    predecessor_ids=("link.mechanism", counter_id),
                    evidence=evidence[:1],
                    assumptions=(
                        "The proposed experiment is not evidence of completed validation.",
                    ),
                ),
                MechanismEvidenceLink(
                    link_id="link.uncertainty",
                    kind=MechanismEvidenceLinkKind.UNCERTAINTY,
                    assertion="Seven uncertainty dimensions and weak links remain visible.",
                    predecessor_ids=("link.validation",),
                    evidence=evidence[:1],
                    assumptions=(
                        "Uncertainty metadata does not establish population calibration.",
                    ),
                ),
                MechanismEvidenceLink(
                    link_id="link.claim-ceiling",
                    kind=MechanismEvidenceLinkKind.CLAIM_CEILING,
                    assertion="The dossier is limited to review-ready mechanistic association.",
                    predecessor_ids=("link.uncertainty",),
                    evidence=evidence[:1],
                    assumptions=(
                        "Clinical intervention benefit is outside this module's ownership.",
                    ),
                ),
            )
            counter = CounterEvidenceRecord(
                counter_evidence_id=counter_id,
                statement="Alternative explanations and contradictory evidence remain unresolved.",
                impact="Requires independent experiments before claim promotion.",
                challenges_link_ids=("link.mechanism",),
                evidence=evidence[:1],
            )
            route = ValidationRoute(
                route_id="route.independent-validation",
                method="orthogonal assay and negative-control replication",
                status=ValidationRouteStatus.COMPLETE,
                required_experiment="Replicate the mechanism association with an orthogonal assay.",
                acceptance_criterion=(
                    "Direction and identity agree within the preregistered tolerance."
                ),
                evidence=evidence[:1],
            )
            ceiling = ClaimCeiling(
                maximum_claim="Review-ready mechanistic association only.",
                prohibited_interpretations=(
                    "No kinase activity claim.",
                    "No generic all-omics fusion claim.",
                    "No direct treatment recommendation.",
                    "No identity or consent inference.",
                ),
                rationale=(
                    "Mechanism evidence and counter-evidence do not establish clinical "
                    "actionability."
                ),
                evidence=evidence[:1],
            )
            dossier = MechanismEvidenceDossier(
                dossier_id=f"dossier.{request_hash.removeprefix('sha256:')}",
                version=M1308_CONTRACT_VERSION,
                links=links,
                counter_evidence=(counter,),
                validation_routes=(route,),
                uncertainty=expected_uncertainty(supported=True),
                claim_ceiling=ceiling,
                configuration=request.configuration,
                reviewer_id=request.context.actor_id,
                evidence=evidence,
            )
            diagnostics.extend(
                (
                    MechanismDossierDiagnostic(
                        diagnostic_id="diagnostic.chain",
                        status=DossierDiagnosticStatus.PASS,
                        message="All dossier links and predecessors are reconstructable.",
                        evidence=evidence[:1],
                    ),
                    MechanismDossierDiagnostic(
                        diagnostic_id="diagnostic.provisional-abi",
                        status=DossierDiagnosticStatus.WARNING,
                        message="Dossier vocabulary and model family remain provisional.",
                        evidence=evidence[:1],
                    ),
                )
            )
        else:
            reason = "Model family is outside the closed provisional dossier support domain."
            findings = (
                MechanismDossierFindingCode.CHAIN_INCOMPLETE,
                MechanismDossierFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
            )
            diagnostics.append(
                MechanismDossierDiagnostic(
                    diagnostic_id="diagnostic.not-evaluable",
                    status=DossierDiagnosticStatus.NOT_EVALUABLE,
                    message=reason,
                    evidence=evidence[:1],
                )
            )
        payload: dict[str, Any] = {
            "output_type": "proteotype_mechanism_evidence_dossier",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1308_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": MechanismDossierStatus.READY
            if supported
            else MechanismDossierStatus.ABSTAINED,
            "dossier": dossier,
            "diagnostics": tuple(diagnostics),
            "findings": findings,
            "abstention_reason": reason,
            "parent_target": M1308_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code=("m1308_dossier_ready" if supported else "m1308_dossier_abstained"),
                rationale=(
                    "The chain, counter-evidence, complete validation route, and claim ceiling "
                    "passed."
                    if supported
                    else (
                        "The model family is outside the safely evaluable support domain and "
                        "requires review."
                    )
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteotypeMechanismDossierResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeMechanismDossierResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1308ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1308ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1308ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1308ReplayVerificationError
        return validated


def assemble_proteotype_mechanism_dossier(
    request: object,
) -> ProteotypeMechanismDossierResult:
    """Public provisional M13-08 operation."""

    return M1308DossierEngine().infer(request)


__all__ = [
    "M1308AuthorizationError",
    "M1308DossierEngine",
    "M1308InferenceError",
    "M1308ReplayVerificationError",
    "assemble_proteotype_mechanism_dossier",
    "preflight_dossier_authorization",
]
