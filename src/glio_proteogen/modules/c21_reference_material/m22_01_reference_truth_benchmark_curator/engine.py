"""Deterministic, caller-declared M22-01 reference-truth curation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_01.canonical import (
    canonical_request_digest,
    normalized_request,
    reference_truth_package_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.contracts.m22_01.v1 import (
    M2201_CONTRACT_VERSION,
    M2201_MODULE_ID,
    AdjudicationStatus,
    CurateProteinRnaDiscordanceReferenceTruthRequest,
    CurationFinding,
    CurationFindingCode,
    CurationStatus,
    ProteinRnaDiscordanceReferenceTruthResult,
    ReferenceTruthPackage,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(CurateProteinRnaDiscordanceReferenceTruthRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M22-01 curation requires accepted configuration, resolved identity, granted consent, "
    "accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_reference_truth",
        statement=(
            "Reference identity, labels, provenance, adjudication, leakage audits and lock "
            "evidence are caller-declared; issuer authority is not authenticated."
        ),
    ),
    Limitation(
        code="protein_rna_discordance_parent_boundary",
        statement=(
            "The package supports benchmark material for protein-RNA discordance but does not "
            "emit a discordance estimate or biological truth claim."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "KINOPHOS kinase-state ownership, generic all-omics fusion, treatment recommendation, "
            "identity inference and unsupported-to-negative conversion are outside this module."
        ),
    ),
)


class M2201AuthorizationError(ValueError):
    """Raised when caller-declared controls do not authorize execution."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2201ReplayError(ValueError):
    """Raised when an immutable M22-01 result fails replay closure."""


class M2201ReferenceTruthBenchmarkCurator:
    """Validate, lock, and replay one M22-01 reference-truth request."""

    __slots__ = ()

    def curate(
        self,
        request: object,
    ) -> ProteinRnaDiscordanceReferenceTruthResult:
        preflight_m2201_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        package = None if findings else _locked_package(canonical)
        status = CurationStatus.CURATED if package is not None else CurationStatus.ABSTAINED
        payload: dict[str, Any] = {
            "output_type": "protein_rna_discordance_reference_truth",
            "result_id": result_identifier(canonical),
            "result_version": M2201_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "package": package,
            "findings": findings,
            "abstention_reason": (
                None
                if package is not None
                else "Reference package was not safely lockable under the declared controls."
            ),
            "parent_target": "protein-RNA discordance",
            "emits_parent": False,
            "support_decision": _support(curated=package is not None),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        provisional = ProteinRnaDiscordanceReferenceTruthResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteinRnaDiscordanceReferenceTruthResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )

    def verify_replay(
        self,
        result: ProteinRnaDiscordanceReferenceTruthResult,
    ) -> ProteinRnaDiscordanceReferenceTruthResult:
        """Re-curate the bound request and compare the complete result."""

        if result.request_digest != canonical_request_digest(result.request):
            raise M2201ReplayError("M22-01 result request digest mismatch")  # noqa: TRY003
        if result.result_id != result_identifier(result.request):
            raise M2201ReplayError("M22-01 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2201ReplayError("M22-01 result payload digest mismatch")  # noqa: TRY003
        try:
            replayed = ProteinRnaDiscordanceReferenceTruthResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
            expected = self.curate(replayed.request)
        except Exception as error:
            raise M2201ReplayError from error
        if canonical_json_bytes(expected) != canonical_json_bytes(replayed):
            raise M2201ReplayError("M22-01 semantic replay mismatch")  # noqa: TRY003
        return replayed


def curate_protein_rna_discordance_reference_truth(
    request: object,
) -> ProteinRnaDiscordanceReferenceTruthResult:
    """Public stateless M22-01 execution entry point."""

    return M2201ReferenceTruthBenchmarkCurator().curate(request)


def preflight_m2201_authorization(candidate: object) -> None:
    """Reject denied controls before traversing reference material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, CurateProteinRnaDiscordanceReferenceTruthRequest)
            else candidate.get("context")
            if isinstance(candidate, Mapping)
            else None
        )
        references = _member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": IdentityLineageState.RESOLVED.value,
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        authorized = all(
            _state_value(_member(_member(references, role), "state")) == state
            for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - fail closed at hostile mapping boundary.
        raise M2201AuthorizationError from None
    if not authorized:
        raise M2201AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def _findings(
    request: CurateProteinRnaDiscordanceReferenceTruthRequest,
) -> tuple[CurationFinding, ...]:
    evidence = _evidence(request)
    findings: list[CurationFinding] = []
    inclusion_by_id = {item.reference_id: item for item in request.inclusions}
    for adjudication in request.adjudications:
        if adjudication.status in {AdjudicationStatus.PENDING, AdjudicationStatus.REVIEWED}:
            findings.append(
                CurationFinding(
                    finding_id=f"m2201.finding.adjudication.{adjudication.reference_id}",
                    code=CurationFindingCode.ADJUDICATION_PENDING,
                    message=(
                        f"Adjudication {adjudication.reference_id} is not locked; reference "
                        "truth is withheld."
                    ),
                    evidence=evidence,
                )
            )
        if (
            adjudication.status is AdjudicationStatus.REJECTED
            and inclusion_by_id[adjudication.reference_id].included
        ):
            findings.append(
                CurationFinding(
                    finding_id=f"m2201.finding.lock.{adjudication.reference_id}",
                    code=CurationFindingCode.LOCK_INCOMPLETE,
                    message=(
                        f"Rejected adjudication {adjudication.reference_id} remains included."
                    ),
                    evidence=evidence,
                )
            )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _locked_package(
    request: CurateProteinRnaDiscordanceReferenceTruthRequest,
) -> ReferenceTruthPackage:
    base: dict[str, object] = {
        "package_id": "m2201.package." + canonical_request_digest(request).removeprefix("sha256:"),
        "version": request.configuration.version,
        "endpoint": request.endpoint,
        "references": request.references,
        "controls": request.controls,
        "inclusions": request.inclusions,
        "adjudications": request.adjudications,
        "challenge_set_ids": request.challenge_set_ids,
        "configuration": request.configuration,
        "lock_digest": "sha256:" + ("0" * 64),
        "locked": True,
        "evidence": _evidence(request),
    }
    provisional = ReferenceTruthPackage.model_construct(**cast("Any", base))
    base["lock_digest"] = reference_truth_package_digest(provisional)
    return ReferenceTruthPackage(**cast("Any", base))


def _support(*, curated: bool) -> SupportDecision:
    if curated:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="locked_reference_truth_package",
            rationale="All declared controls, adjudications and lock fields are closed.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="reference_truth_package_abstained",
        rationale="Reference truth remains withheld until the declared package is reviewable.",
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M22-01 does not infer {dimension} uncertainty from caller material.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=("No biological truth uncertainty is inferred.",),
    )


def _evidence(
    request: CurateProteinRnaDiscordanceReferenceTruthRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M22-01 source artifact; issuer authority is not authenticated.",
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: CurateProteinRnaDiscordanceReferenceTruthRequest,
    request_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=str(decision.state.value),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id="m2201.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2201_MODULE_ID,
        module_version=M2201_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=canonical_request_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2201AuthorizationError",
    "M2201ReferenceTruthBenchmarkCurator",
    "M2201ReplayError",
    "curate_protein_rna_discordance_reference_truth",
    "preflight_m2201_authorization",
]
