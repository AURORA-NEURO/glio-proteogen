"""Deterministic, caller-declared M21-01 reference-truth curator.

M21-01 never authenticates an issuer, searches raw molecular data, infers
identity, or relabels an upstream result.  It validates the explicitly
declared reference package, applies the seven upstream control gates, and
emits either a locked package or a typed abstention envelope.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_01.canonical import (
    canonical_request_digest,
    normalized_request,
    package_lock_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.contracts.m21_01.v1 import (
    M2101_CONTRACT_VERSION,
    M2101_MODULE_ID,
    AdjudicationStatus,
    ComplexActivityReferenceTruthResult,
    CurateComplexActivityReferenceTruthRequest,
    CurationFinding,
    CurationFindingCode,
    CurationStatus,
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
from glio_proteogen.kernel.strict_json import strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(CurateComplexActivityReferenceTruthRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "M21-01 reference curation requires accepted configuration, resolved identity, "
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
        code="complex_activity_parent_boundary",
        statement=(
            "The package supports benchmark material for the complex-activity parent but does "
            "not emit a complex-activity estimate or biological truth claim."
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


class M2101AuthorizationError(ValueError):
    """Raised when caller-declared upstream controls do not authorize execution."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M2101ReferenceTruthBenchmarkCurator:
    """Validate, lock, and replay one M21-01 reference-truth request."""

    __slots__ = ()

    def curate(self, request: object) -> ComplexActivityReferenceTruthResult:
        preflight_m2101_authorization(request)
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
            "output_type": "complex_activity_reference_truth",
            "result_id": result_identifier(canonical),
            "result_version": M2101_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": "sha256:" + ("0" * 64),
            "request": canonical,
            "status": status,
            "package": package,
            "findings": findings,
            "abstention_reason": None
            if package is not None
            else "Reference package was not safely lockable under the declared controls.",
            "parent_target": "complex activity",
            "emits_parent": False,
            "support_decision": _support(curated=package is not None),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": _evidence(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        materialized = cast(
            "dict[str, Any]",
            strict_json_loads(canonical_json_bytes(payload)),
        )
        payload["result_digest"] = result_payload_digest(materialized)
        return ComplexActivityReferenceTruthResult.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )

    def verify_replay(
        self,
        result: ComplexActivityReferenceTruthResult,
    ) -> ComplexActivityReferenceTruthResult:
        """Revalidate an immutable result and return the exact replayed value."""

        return ComplexActivityReferenceTruthResult.model_validate_json(
            canonical_json_bytes(result),
            strict=True,
        )


def curate_complex_activity_reference_truth(
    request: object,
) -> ComplexActivityReferenceTruthResult:
    """Public stateless M21-01 execution entry point."""

    return M2101ReferenceTruthBenchmarkCurator().curate(request)


def preflight_m2101_authorization(candidate: object) -> None:
    """Reject denied controls before traversing reference material."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, CurateComplexActivityReferenceTruthRequest)
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
        raise M2101AuthorizationError from None
    if not authorized:
        raise M2101AuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _findings(
    request: CurateComplexActivityReferenceTruthRequest,
) -> tuple[CurationFinding, ...]:
    evidence = _evidence(request)
    findings: list[CurationFinding] = []
    for adjudication in request.adjudications:
        if adjudication.status in {AdjudicationStatus.PENDING, AdjudicationStatus.REVIEWED}:
            findings.extend(
                [
                    CurationFinding(
                        finding_id=f"finding.adjudication.{adjudication.reference_id}",
                        code=CurationFindingCode.ADJUDICATION_PENDING,
                        message=(
                            f"Adjudication {adjudication.reference_id} is not locked; "
                            "reference truth is withheld."
                        ),
                        evidence=evidence,
                    )
                ]
            )
    inclusion_by_id = {item.reference_id: item for item in request.inclusions}
    for adjudication in request.adjudications:
        if (
            adjudication.status is AdjudicationStatus.REJECTED
            and inclusion_by_id[adjudication.reference_id].included
        ):
            findings.extend(
                [
                    CurationFinding(
                        finding_id=f"finding.lock.{adjudication.reference_id}",
                        code=CurationFindingCode.LOCK_INCOMPLETE,
                        message=(
                            f"Rejected adjudication {adjudication.reference_id} remains included."
                        ),
                        evidence=evidence,
                    )
                ]
            )
    return tuple(sorted(findings, key=lambda item: item.finding_id))


def _locked_package(request: CurateComplexActivityReferenceTruthRequest) -> ReferenceTruthPackage:
    challenge_set_ids = tuple(
        item.reference_id for item in request.references if item.challenge_set
    )
    base: dict[str, object] = {
        "package_id": "m2101.package." + canonical_request_digest(request).removeprefix("sha256:"),
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
            rationale=f"M21-01 does not infer {dimension} uncertainty from caller material.",
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
            "Uncertainty is preserved from the caller-declared reference package; "
            "no biological truth is inferred.",
        ),
    )


def _evidence(
    request: CurateComplexActivityReferenceTruthRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M21-01 source artifact; issuer authority is not authenticated.",
        )
        for artifact in request.source_artifacts
    )


def _provenance(
    request: CurateComplexActivityReferenceTruthRequest,
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
        activity_id="m2101.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2101_MODULE_ID,
        module_version=M2101_CONTRACT_VERSION,
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
    "M2101AuthorizationError",
    "M2101ReferenceTruthBenchmarkCurator",
    "curate_complex_activity_reference_truth",
    "preflight_m2101_authorization",
]
