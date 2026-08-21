"""Deterministic retirement, preservation and knowledge-transfer engine."""

# ruff: noqa: TRY003, B009, C901
from __future__ import annotations

from typing import Final

from glio_proteogen.contracts.m27_08 import (
    ArchiveStatus,
    ComplexActivityRetirementResult,
    MigrationStatus,
    RetireComplexActivityServiceRequest,
    RetirementFinding,
    RetirementFindingCode,
    RetirementPackage,
    RetirementRunStatus,
    RetirementStatus,
)
from glio_proteogen.contracts.m27_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
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

_CONTROL_ROLES: Final = (
    ControlRole.APPROVED_CONFIGURATION,
    ControlRole.IDENTITY_LINEAGE,
    ControlRole.PROVENANCE,
    ControlRole.CONSENT,
    ControlRole.QUALITY,
    ControlRole.SUPPORT,
    ControlRole.INTENDED_USE,
)
_M2707_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-07+json"


class RetirementAuthorizationError(ValueError):
    """Request failed the retirement authorization firewall."""


class RetirementReplayError(ValueError):
    """Result failed deterministic replay verification."""


def preflight_retirement_authorization(request: RetireComplexActivityServiceRequest) -> None:
    if request.context.request_id != request.request_id:
        raise RetirementAuthorizationError("request context identity mismatch")
    consent_state = getattr(
        request.context.references.consent.state, "value", request.context.references.consent.state
    )
    if consent_state != "granted":
        raise RetirementAuthorizationError("consent is not granted")
    identity_state = getattr(
        request.context.references.identity_lineage.state,
        "value",
        request.context.references.identity_lineage.state,
    )
    if identity_state != "resolved":
        raise RetirementAuthorizationError("identity lineage is unresolved")
    for role in _CONTROL_ROLES:
        reference = getattr(request.context.references, role.value)
        state = getattr(reference.state, "value", reference.state)
        if role is ControlRole.IDENTITY_LINEAGE and state == "resolved":
            continue
        if role is ControlRole.CONSENT and state == "granted":
            continue
        if state != "accepted":
            raise RetirementAuthorizationError("required control is not accepted")
    if not request.source_artifacts:
        raise RetirementAuthorizationError("at least one source artifact is required")
    if len({item.artifact_id for item in request.source_artifacts}) != len(
        request.source_artifacts
    ):
        raise RetirementAuthorizationError("source artifact ids must be unique")
    if any(item.media_type != _M2707_INPUT_MEDIA_TYPE for item in request.source_artifacts):
        raise RetirementAuthorizationError("unsupported upstream artifact media type")


def _uncertainty() -> UncertaintyProfile:
    def unavailable(text: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=text)

    return UncertaintyProfile(
        measurement=unavailable("Retirement does not estimate scientific measurements."),
        sampling=unavailable("No sampling population is modeled."),
        parameter=unavailable("No fitted parameters are used."),
        model_form=unavailable("Deterministic retirement policy has no model form."),
        identification=unavailable("Identity is consumed as a control, not inferred."),
        support=unavailable("Support follows explicit preservation and rollback controls."),
        transport=unavailable("External authority is not authenticated by this service."),
    )


def _evidence(request: RetireComplexActivityServiceRequest) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    return tuple(
        EvidenceReference(
            reference=getattr(refs, role.value).evidence,
            role="evidence",
            claim=f"control:{role.value}",
        )
        for role in _CONTROL_ROLES
    )


def _provenance(request: RetireComplexActivityServiceRequest, digest: str) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m2708.{digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M27-08",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(
            digest,
            request.mass_spectrometry_proteome.digest,
            request.genome_transcriptome.digest,
            request.ptm_annotations.digest,
            *(item.digest for item in request.source_artifacts),
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=getattr(refs, role.value).decision_id,
                state=getattr(getattr(refs, role.value), "state").value,
                policy_version=getattr(refs, role.value).policy_version,
                evidence_digest=getattr(refs, role.value).evidence.digest,
                subject_digest=(
                    refs.identity_lineage.binding_digest
                    if role is ControlRole.IDENTITY_LINEAGE
                    else None
                ),
            )
            for role in _CONTROL_ROLES
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement="The M27-08 ABI is provisional pending owner confirmation.",
        ),
        Limitation(
            code="caller_declared",
            statement="Retirement and archive values are caller-declared metadata.",
        ),
        Limitation(
            code="no_biology",
            statement="No protein, proteoform, isoform, or glioma-biology inference is emitted.",
        ),
    )


class M2708RetirementEngine:
    """Build and replay executed or safely abstained retirement results."""

    def evaluate(
        self, request: RetireComplexActivityServiceRequest
    ) -> ComplexActivityRetirementResult:
        preflight_retirement_authorization(request)
        digest = canonical_request_digest(request)
        evidence = _evidence(request)
        unsatisfied = any(not item.satisfied for item in request.criteria)
        incomplete = any(
            item.status is not MigrationStatus.COMPLETED for item in request.migrations
        )
        missing_evidence = any(not item.retrievable for item in request.preserved_evidence)
        unacknowledged = any(not item.acknowledged for item in request.communications)
        archive_unverified = request.archive.status is not ArchiveStatus.VERIFIED
        # ``status`` is the governed migration state.  Identifiers are opaque
        # caller labels and must never be interpreted as operational state.
        active = any(item.status is MigrationStatus.IN_PROGRESS for item in request.migrations)
        failed = (
            unsatisfied
            or incomplete
            or missing_evidence
            or unacknowledged
            or archive_unverified
            or active
        )
        findings: list[RetirementFinding] = []
        if unsatisfied:
            findings.append(
                RetirementFinding(
                    finding_id=f"finding.m2708.{digest[-12:]}-criteria",
                    code=RetirementFindingCode.CRITERION_UNSATISFIED,
                    message="A retirement criterion is unsatisfied.",
                    evidence=evidence[:1],
                )
            )
        if incomplete:
            findings.append(
                RetirementFinding(
                    finding_id=f"finding.m2708.{digest[-12:]}-migration",
                    code=RetirementFindingCode.DEPENDENCY_MIGRATION_INCOMPLETE,
                    message="Dependency migration is incomplete.",
                    evidence=evidence[:1],
                )
            )
        if missing_evidence:
            findings.append(
                RetirementFinding(
                    finding_id=f"finding.m2708.{digest[-12:]}-evidence",
                    code=RetirementFindingCode.EVIDENCE_NOT_RETRIEVABLE,
                    message="Preserved evidence is not retrievable.",
                    evidence=evidence[:1],
                )
            )
        if unacknowledged:
            findings.append(
                RetirementFinding(
                    finding_id=f"finding.m2708.{digest[-12:]}-communication",
                    code=RetirementFindingCode.COMMUNICATION_UNACKNOWLEDGED,
                    message="Retirement communication has not been acknowledged.",
                    evidence=evidence[:1],
                )
            )
        if archive_unverified:
            findings.append(
                RetirementFinding(
                    finding_id=f"finding.m2708.{digest[-12:]}-archive",
                    code=RetirementFindingCode.ARCHIVE_UNVERIFIED,
                    message="Long-term archive is not verified.",
                    evidence=evidence[:1],
                )
            )
        if active:
            findings.append(
                RetirementFinding(
                    finding_id=f"finding.m2708.{digest[-12:]}-active",
                    code=RetirementFindingCode.ACTIVE_DEPENDENCY,
                    message="An active dependency remains.",
                    evidence=evidence[:1],
                )
            )
        package = None
        status = RetirementRunStatus.ABSTAINED if failed else RetirementRunStatus.EXECUTED
        support = SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED if failed else SupportStatus.SUPPORTED,
            reason_code="retirement_review_required" if failed else "retirement_controls_passed",
            rationale="Retirement remains review-bound and does not assert external authority.",
        )
        if not failed:
            package = RetirementPackage(
                package_id=f"package.m2708.{digest.removeprefix('sha256:')[:16]}",
                version="1.0.0",
                status=RetirementStatus.EXECUTED,
                criteria=request.criteria,
                migrations=request.migrations,
                preserved_evidence=request.preserved_evidence,
                communications=request.communications,
                archive=request.archive,
                configuration=request.configuration,
                evidence=evidence,
            )
        candidate = ComplexActivityRetirementResult.model_construct(
            result_id=f"result.m2708.{digest.removeprefix('sha256:')}",
            result_version="0.1.0-provisional",
            request_digest=digest,
            result_digest="sha256:" + "0" * 64,
            request=request,
            status=status,
            package=package,
            findings=tuple(findings),
            abstention_reason=(
                "retirement criteria or preservation controls require review" if failed else None
            ),
            parent_target="complex activity",
            emits_parent=False,
            support_decision=support,
            uncertainty=_uncertainty(),
            provenance=_provenance(request, digest),
            evidence=evidence,
            limitations=_limitations(),
            human_review_required=True,
        )
        return ComplexActivityRetirementResult(
            **{**candidate.model_dump(), "result_digest": result_payload_digest(candidate)}
        )

    def replay(self, result: ComplexActivityRetirementResult) -> ComplexActivityRetirementResult:
        # Re-validate the serialized envelope first.  ``model_copy(update=...)``
        # intentionally bypasses Pydantic validators, so checking only the
        # supplied payload digest would accept a stale request digest/result ID
        # paired with a self-rehashed retirement package.
        try:
            validated = ComplexActivityRetirementResult.model_validate_json(
                canonical_json_bytes(result), strict=True
            )
        except Exception as error:
            raise RetirementReplayError("retirement result envelope is invalid") from error
        if validated.request_digest != canonical_request_digest(validated.request):
            raise RetirementReplayError("retirement request digest mismatch")
        expected_id = f"result.m2708.{validated.request_digest.removeprefix('sha256:')}"
        if validated.result_id != expected_id:
            raise RetirementReplayError("retirement result identifier mismatch")
        if validated.result_digest != result_payload_digest(validated):
            raise RetirementReplayError("result digest mismatch")
        try:
            recomputed = self.evaluate(validated.request)
        except Exception as error:
            raise RetirementReplayError("retirement result replay failed") from error
        if recomputed.model_dump(mode="json") != validated.model_dump(mode="json"):
            raise RetirementReplayError("retirement result replay differs from request")
        return validated


def retire_complex_activity_service(
    request: RetireComplexActivityServiceRequest,
) -> ComplexActivityRetirementResult:
    return M2708RetirementEngine().evaluate(request)


__all__ = [
    "M2708RetirementEngine",
    "RetirementAuthorizationError",
    "RetirementReplayError",
    "preflight_retirement_authorization",
    "retire_complex_activity_service",
]
