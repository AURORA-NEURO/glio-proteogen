"""Deterministic M25-01 reference-truth curation runtime.

The runtime validates caller-declared benchmark material, applies the seven
upstream controls before reading package members, and emits either a locked
package or a typed abstention. It does not authenticate an issuer, inspect
scientific payloads, or infer biological truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_01.canonical import (
    canonical_request_digest,
    normalized_request,
    package_lock_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.contracts.m25_01.v1 import (
    M2501_CONTRACT_VERSION,
    M2501_MODULE_ID,
    AdjudicationStatus,
    CurateProteotypeReferenceTruthRequest,
    CurationFinding,
    CurationFindingCode,
    CurationStatus,
    ProteotypeReferenceTruthResult,
    ReferenceTruthPackage,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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

_REQUEST_ADAPTER: Final = TypeAdapter(CurateProteotypeReferenceTruthRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M25-01 reference curation requires accepted configuration, resolved identity, "
    "granted consent, accepted provenance/quality/support/intended-use controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_reference_truth",
        statement=(
            "Reference identity, labels, provenance, adjudication, leakage audits and lock "
            "evidence are caller-declared; issuer authority and laboratory execution are not "
            "authenticated."
        ),
    ),
    Limitation(
        code="proteotype_parent_boundary",
        statement=(
            "The package supports benchmark material for the proteotype parent but does not "
            "emit a proteotype estimate or biological truth claim."
        ),
    ),
    Limitation(
        code="exclusive_scope",
        statement=(
            "Kinase-state ownership, generic all-omics fusion, treatment recommendation, "
            "identity inference, consent inference and unsupported-to-negative conversion "
            "are outside this module."
        ),
    ),
)


class M2501AuthorizationError(ValueError):
    """Raised when caller-declared upstream controls do not authorize execution."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2501ReplayError(ValueError):
    """Raised when an immutable result cannot be replayed exactly."""

    def __init__(self, message: str = "M25-01 replay verification failed") -> None:
        super().__init__(message)


class M2501ReferenceTruthBenchmarkCurator:
    """Validate, lock, and replay one caller-declared M25-01 package."""

    __slots__ = ()

    def curate(self, request: object) -> ProteotypeReferenceTruthResult:
        preflight_m2501_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)),
            strict=True,
        )
        request_digest = canonical_request_digest(canonical)
        findings = _findings(canonical)
        package = None if findings else _locked_package(canonical)
        status = CurationStatus.CURATED if package is not None else CurationStatus.ABSTAINED
        payload: dict[str, Any] = {
            "output_type": "proteotype_reference_truth",
            "result_id": result_identifier(canonical, status.value),
            "result_version": M2501_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "package": package,
            "findings": findings,
            "abstention_reason": None
            if package is not None
            else "Reference package was not safely lockable under the declared controls.",
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": _support(curated=package is not None),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        provisional = ProteotypeReferenceTruthResult.model_construct(**cast("Any", payload))
        payload["result_digest"] = result_payload_digest(provisional)
        return ProteotypeReferenceTruthResult.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )

    def verify_replay(
        self,
        result: ProteotypeReferenceTruthResult,
    ) -> ProteotypeReferenceTruthResult:
        """Revalidate an immutable result and all canonical digest closures.

        Digest checks alone only prove that a payload was rehashed.  Rebuild the
        result from its bound request and compare the complete canonical result
        so callers cannot alter evidence, limitations, support, or status and
        then make the forged object internally self-consistent.
        """

        try:
            replayed = ProteotypeReferenceTruthResult.model_validate_json(
                canonical_json_bytes(result),
                strict=True,
            )
            expected = self.curate(replayed.request)
        except Exception as error:
            raise M2501ReplayError from error
        if replayed.result_id != result_identifier(replayed.request, replayed.status.value):
            raise M2501ReplayError
        if replayed.request_digest != canonical_request_digest(replayed.request):
            raise M2501ReplayError
        if replayed.result_digest != result_payload_digest(replayed):
            raise M2501ReplayError
        if replayed.package is not None and replayed.package.lock_digest != package_lock_digest(
            replayed.package
        ):
            raise M2501ReplayError
        if canonical_json_bytes(expected) != canonical_json_bytes(replayed):
            raise M2501ReplayError
        return replayed


def curate_proteotype_reference_truth(
    request: object,
) -> ProteotypeReferenceTruthResult:
    """Public stateless M25-01 execution entry point."""

    return M2501ReferenceTruthBenchmarkCurator().curate(request)


def preflight_m2501_authorization(candidate: object) -> None:
    """Reject denied controls before traversing caller-declared package members."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, CurateProteotypeReferenceTruthRequest)
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
            _member(_member(references, role), "state") == state for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - fail closed at hostile mapping boundary.
        raise M2501AuthorizationError from None
    if not authorized:
        raise M2501AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _findings(
    request: CurateProteotypeReferenceTruthRequest,
) -> tuple[CurationFinding, ...]:
    evidence = _evidence(request)
    findings: list[CurationFinding] = []
    inclusion_by_id = {item.reference_id: item for item in request.inclusions}
    for adjudication in request.adjudications:
        if adjudication.status in {AdjudicationStatus.PENDING, AdjudicationStatus.REVIEWED}:
            findings.append(
                CurationFinding(
                    finding_id=f"finding.adjudication.{adjudication.reference_id}",
                    code=CurationFindingCode.ADJUDICATION_PENDING,
                    message=(
                        f"Adjudication {adjudication.reference_id} is not locked; "
                        "reference truth is withheld."
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
                    finding_id=f"finding.lock.{adjudication.reference_id}",
                    code=CurationFindingCode.LOCK_INCOMPLETE,
                    message=(
                        f"Rejected adjudication {adjudication.reference_id} remains included."
                    ),
                    evidence=evidence,
                )
            )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _locked_package(request: CurateProteotypeReferenceTruthRequest) -> ReferenceTruthPackage:
    challenge_set_ids = tuple(
        item.reference_id for item in request.references if item.challenge_set
    )
    base: dict[str, object] = {
        "package_id": "m2501.package." + canonical_request_digest(request).removeprefix("sha256:"),
        "version": request.configuration.version,
        "endpoint": request.endpoint,
        "references": request.references,
        "controls": request.controls,
        "inclusions": request.inclusions,
        "adjudications": request.adjudications,
        "challenge_set_ids": challenge_set_ids,
        "configuration": request.configuration,
        "lock_digest": "sha256:" + ("0" * 64),
        "locked": True,
        "evidence": _evidence(request),
    }
    provisional = ReferenceTruthPackage.model_construct(**cast("Any", base))
    base["lock_digest"] = package_lock_digest(provisional)
    return ReferenceTruthPackage(**cast("Any", base))


def _support(*, curated: bool) -> SupportDecision:
    if curated:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="locked_reference_truth_package",
            rationale=(
                "All declared controls, leakage audits, adjudications and lock fields are closed."
            ),
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="reference_truth_package_abstained",
        rationale=(
            "Reference truth remains withheld until the declared package is reviewable "
            "and lockable."
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M25-01 does not infer {dimension} uncertainty from caller material.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Uncertainty is preserved from caller-declared reference material; no biological "
            "truth is inferred.",
        ),
    )


def _evidence(
    request: CurateProteotypeReferenceTruthRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M25-01 source artifact; issuer authority is not authenticated.",
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: CurateProteotypeReferenceTruthRequest,
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
        activity_id="m2501.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2501_MODULE_ID,
        module_version=M2501_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            *tuple(artifact.digest for artifact in request.source_artifacts),
            sha256_digest(request.configuration),
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


__all__ = [
    "M2501AuthorizationError",
    "M2501ReferenceTruthBenchmarkCurator",
    "M2501ReplayError",
    "curate_proteotype_reference_truth",
    "preflight_m2501_authorization",
]
